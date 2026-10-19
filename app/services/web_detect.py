"""Détection de l'interface web d'administration des équipements IT.

Principes :
- contrôles TCP asynchrones avec timeouts courts et concurrence limitée ;
- ports limités : 80/443 + ports connus/justifiés par le type d'équipement
  (jamais de balayage de plage large) ;
- requête HTTP(S) légère pour distinguer une vraie interface web d'une simple
  réponse TCP ;
- 401/403 = interface protégée (jamais une panne) ;
- les certificats TLS sont TOUJOURS vérifiés (aucun contournement) : un
  certificat non fiable est signalé via le statut "tls_untrusted" ;
- cibles et redirections validées contre l'inventaire + les plages réseau
  configurées (protection SSRF) ; seuls http/https sont acceptés ;
- aucun identifiant ni mot de passe n'est intégré, récupéré ou stocké.
"""

import asyncio
import ipaddress
import socket
import ssl
from datetime import UTC, datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ITAsset, NetworkRange

# États possibles de l'URL de gestion (colonnes management_url_status)
STATUS_ACCESSIBLE = "accessible"        # le service répond en HTTP
STATUS_AUTH_REQUIRED = "auth_required"  # 401/403 : interface protégée
STATUS_UNREACHABLE = "unreachable"      # pas de réponse HTTP valide
STATUS_TLS_UNTRUSTED = "tls_untrusted"  # certificat TLS non fiable (signalé)
STATUS_TO_CHECK = "to_check"            # jamais vérifié / à vérifier

_SOURCE_AUTO = "auto"

# Ports par défaut et ports justifiés par le type d'équipement.
_DEFAULT_PORTS: Tuple[int, ...] = (80, 443)
_PORTS_BY_TYPE = {
    "printer": (80, 443, 631),      # 631 : impression IPP (serveur web CUPS)
    "switch": (80, 443, 8080, 8443),
    "router": (80, 443, 8080, 8443),
    "firewall": (80, 443, 8443, 8080),
    "access_point": (80, 443, 8080, 8443),
    "server": (80, 443, 8080),
}
_HTTPS_PORTS = (443, 8443)
_MAX_CANDIDATE_PORTS = 6
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
# Corps lu au maximum par requête : seuls les en-têtes importent.
_MAX_BODY_BYTES = 512
# Fenêtre résiduelle DNS : la résolution est revalidée avant chaque requête.
_DNS_TIMEOUT_SECONDS = 5.0

# Préférence entre résultats concurrents de ports différents.
_STATUS_PREFERENCE = {
    STATUS_ACCESSIBLE: 0,
    STATUS_AUTH_REQUIRED: 1,
    STATUS_TLS_UNTRUSTED: 2,
    STATUS_UNREACHABLE: 3,
}


def validate_management_url(url: Optional[str]) -> Optional[str]:
    """Valider une URL de gestion saisie manuellement.

    Seuls http/https, sans identifiants embarqués. Retourne "" pour un champ
    vide (effacement de l'URL), lève ValueError si l'URL est invalide.
    """
    if url is None:
        return None
    url = str(url).strip()
    if not url:
        return ""
    if len(url) > 500:
        raise ValueError("URL trop longue (500 caractères max)")
    if any(char in url for char in ("\r", "\n", "\t", " ")):
        raise ValueError("URL invalide (caractères interdits)")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Seuls les schémas http et https sont acceptés")
    if not parsed.hostname:
        raise ValueError("L'URL doit contenir un hôte")
    if parsed.username or parsed.password:
        raise ValueError("Les identifiants dans l'URL sont refusés")
    return url


def _format_host(host: str) -> str:
    """Encadrer une IPv6 pour la construire dans une URL."""
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def _build_url(scheme: str, host: str, port: int, path: str = "/") -> str:
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = _format_host(host) if default_port else f"{_format_host(host)}:{port}"
    if not path.startswith("/"):
        path = "/" + path
    return f"{scheme}://{netloc}{path}"


def _is_cert_error(exc: BaseException) -> bool:
    """Détecter un problème de CERTIFICAT (et non un simple échec TLS).

    Un échec de handshake générique (ex. HTTP servi sur un port HTTPS) n'est
    pas un problème de confiance : seul un certificat non fiable est signalé
    via le statut tls_untrusted. La vérification reste TOUJOURS active.
    """
    current: Optional[BaseException] = exc
    seen = 0
    while current is not None and seen < 10:
        if isinstance(current, ssl.SSLCertVerificationError):
            return True
        message = str(current).lower()
        if (
            "certificate verify failed" in message
            or "certificate_verify_failed" in message
            or "self signed certificate" in message
            or "self-signed certificate" in message
            or "unable to get local issuer" in message
        ):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


class WebInterfaceDetector:
    """Probe HTTP(S) limité sur les équipements de l'inventaire.

    ``verify`` ne doit JAMAIS être positionné à False en production : les
    tests injectent un magasin de confiance personnalisé (CA de test) afin
    de garder la vérification active.
    """

    def __init__(self, db: AsyncSession, verify: bool | ssl.SSLContext = True):
        self.db = db
        self.verify = verify
        settings = get_settings()
        self._tcp_timeout = settings.IT_WEB_DETECT_TCP_TIMEOUT
        self._http_timeout = settings.IT_WEB_DETECT_HTTP_TIMEOUT
        self._max_redirects = settings.IT_WEB_DETECT_MAX_REDIRECTS
        self._semaphore = asyncio.Semaphore(max(1, settings.IT_WEB_DETECT_CONCURRENCY))
        self._allowlist_ips: Optional[set] = None
        self._allowlist_networks: Optional[list] = None
        self._allowlist_lock = asyncio.Lock()

    # ------------------------------------------------------------
    # Autorise-liste (inventaire + plages réseau configurées)
    # ------------------------------------------------------------

    async def warmup(self) -> None:
        """Charger l'autorise-liste une seule fois (avant les tâches parallèles)."""
        async with self._allowlist_lock:
            if self._allowlist_ips is not None:
                return
            ips: set = set()
            networks: list = []

            result = await self.db.execute(
                select(ITAsset.ip_address).where(ITAsset.ip_address.isnot(None))
            )
            for (ip,) in result.all():
                try:
                    ips.add(ipaddress.ip_address(str(ip).strip()))
                except ValueError:
                    continue

            result = await self.db.execute(
                select(NetworkRange.cidr).where(NetworkRange.is_active == True)  # noqa: E712
            )
            for (cidr,) in result.all():
                try:
                    networks.append(ipaddress.ip_network(str(cidr), strict=False))
                except ValueError:
                    continue

            self._allowlist_ips = ips
            self._allowlist_networks = networks

    def _ip_allowed(self, ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
        if self._allowlist_ips is None:
            # Non chargé (scan avant warmup) : l'appelant ne fournit que l'IP
            # de l'équipement lui-même, déjà présent dans l'inventaire.
            return True
        if ip in self._allowlist_ips:
            return True
        return any(ip in network for network in self._allowlist_networks)

    async def _resolve_host(self, host: str) -> Optional[List[str]]:
        try:
            loop = asyncio.get_running_loop()
            infos = await asyncio.wait_for(
                loop.getaddrinfo(host, None, type=socket.SOCK_STREAM),
                timeout=_DNS_TIMEOUT_SECONDS,
            )
        except Exception:
            return None
        resolved = sorted({info[4][0] for info in infos if info and info[4]})
        return resolved or None

    async def is_host_allowed(self, host: str) -> Tuple[bool, Optional[str]]:
        """Valider une cible (IP ou hostname) contre l'autorise-liste."""
        host = host.strip().strip("[]")
        if not host:
            return False, "hôte vide"
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            resolved = await self._resolve_host(host)
            if not resolved:
                return False, f"résolution impossible : {host}"
            addresses = []
            for item in resolved:
                try:
                    addresses.append(ipaddress.ip_address(item))
                except ValueError:
                    return False, f"résolution invalide : {item}"
            # Toutes les adresses doivent être autorisées (anti-rebinding).
            for address in addresses:
                if not self._ip_allowed(address):
                    return False, f"adresse non autorisée : {address}"
            return True, None
        if not self._ip_allowed(ip):
            return False, f"adresse non autorisée : {ip}"
        return True, None

    # ------------------------------------------------------------
    # Ports candidats
    # ------------------------------------------------------------

    @staticmethod
    def candidate_ports(asset_type: Optional[str]) -> List[int]:
        settings = get_settings()
        raw = (settings.IT_WEB_DETECT_PORTS or "").strip()
        ports: List[int] = []
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if part.isdigit() and 1 <= int(part) <= 65535:
                    ports.append(int(part))
        if not ports:
            ports = list(_PORTS_BY_TYPE.get(asset_type or "", _DEFAULT_PORTS))
        deduped: List[int] = []
        for port in ports:
            if port not in deduped:
                deduped.append(port)
        return deduped[:_MAX_CANDIDATE_PORTS]

    # ------------------------------------------------------------
    # Contrôle TCP
    # ------------------------------------------------------------

    async def _tcp_open(self, host: str, port: int) -> bool:
        writer = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=self._tcp_timeout
            )
            return True
        except Exception:
            return False
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

    # ------------------------------------------------------------
    # Requête HTTP(S) légère avec redirections validées
    # ------------------------------------------------------------

    async def _get_checked(
        self, client: httpx.AsyncClient, url: str, same_host_only: bool = False
    ) -> dict:
        """Effectuer un GET avec suivi manuel des redirections.

        Chaque saut est validé (schéma http/https, pas d'identifiants, cible
        autorisée) avant d'être suivi. ``same_host_only`` s'applique quand
        l'autorise-liste n'est pas chargée : seules les redirections vers le
        même hôte sont alors acceptées.
        """
        current = url
        last_response: Optional[dict] = None
        redirect_to: Optional[str] = None
        redirect_blocked: Optional[str] = None

        for hop in range(self._max_redirects + 1):
            parsed = urlsplit(current)
            if parsed.scheme not in ("http", "https"):
                return {
                    "http_detected": False,
                    "status": STATUS_UNREACHABLE,
                    "error": f"schéma refusé : {parsed.scheme}",
                    "url": None,
                }
            if parsed.username or parsed.password:
                return {
                    "http_detected": False,
                    "status": STATUS_UNREACHABLE,
                    "error": "identifiants refusés dans l'URL",
                    "url": None,
                }

            allowed, reason = await self.is_host_allowed(parsed.hostname or "")
            if not allowed:
                return {
                    "http_detected": False,
                    "status": STATUS_UNREACHABLE,
                    "error": f"cible refusée : {reason}",
                    "url": None,
                }
            if same_host_only:
                origin = urlsplit(url)
                if (parsed.hostname or "").lower() != (origin.hostname or "").lower():
                    return {
                        "http_detected": False,
                        "status": STATUS_UNREACHABLE,
                        "error": "redirection vers un autre hôte refusée",
                        "url": None,
                        "redirect_blocked": current,
                    }

            try:
                async with client.stream("GET", current) as response:
                    status_code = response.status_code
                    headers = {k.lower(): v for k, v in response.headers.items()}
                    read_bytes = 0
                    async for chunk in response.aiter_bytes():
                        read_bytes += len(chunk)
                        if read_bytes >= _MAX_BODY_BYTES:
                            break
            except Exception as exc:
                if _is_cert_error(exc):
                    return {
                        "http_detected": False,
                        "status": STATUS_TLS_UNTRUSTED,
                        "error": "certificat TLS non fiable (vérification active)",
                        "url": current,
                    }
                return {
                    "http_detected": False,
                    "status": STATUS_UNREACHABLE,
                    "error": str(exc)[:200] or exc.__class__.__name__,
                    "url": current,
                }

            result = {
                "http_detected": True,
                "http_status": status_code,
                "url": current,
                "server": headers.get("server"),
                "www_authenticate": headers.get("www-authenticate"),
                "redirect_to": None,
                "redirect_blocked": None,
                "error": None,
            }
            if status_code in (401, 403):
                result["status"] = STATUS_AUTH_REQUIRED
            else:
                result["status"] = STATUS_ACCESSIBLE

            location = headers.get("location")
            if status_code in _REDIRECT_STATUSES and location:
                next_url = urljoin(current, location)
                next_parsed = urlsplit(next_url)
                if next_parsed.scheme not in ("http", "https") or (
                    next_parsed.username or next_parsed.password
                ):
                    result["redirect_blocked"] = next_url
                    last_response = result
                    break
                allowed_next, next_reason = await self.is_host_allowed(
                    next_parsed.hostname or ""
                )
                if not allowed_next:
                    # SSRF : ne PAS suivre la redirection, mais conserver le
                    # fait que l'interface a répondu.
                    result["redirect_blocked"] = next_url
                    result["redirect_error"] = next_reason
                    last_response = result
                    break
                redirect_to = next_url
                result["redirect_to"] = next_url
                last_response = result
                if hop == self._max_redirects:
                    result["status"] = STATUS_UNREACHABLE
                    result["http_detected"] = False
                    result["error"] = "trop de redirections"
                    break
                current = next_url
                continue

            last_response = result
            break

        # Conserver la dernière redirection suivie (la réponse finale n'a
        # pas de Location) pour l'affichage dans les détails.
        if last_response is not None and redirect_to and not last_response.get("redirect_to"):
            last_response["redirect_to"] = redirect_to

        return last_response or {
            "http_detected": False,
            "status": STATUS_UNREACHABLE,
            "error": "aucune réponse",
            "url": None,
            "redirect_to": redirect_to,
            "redirect_blocked": redirect_blocked,
        }

    async def _probe_port(self, client: httpx.AsyncClient, host: str, port: int) -> dict:
        """Probe un port ouvert : identifie une vraie réponse HTTP."""
        schemes = ("https",) if port in _HTTPS_PORTS else ("http", "https")
        best_error: Optional[dict] = None

        for scheme in schemes:
            url = _build_url(scheme, host, port)
            try:
                result = await self._get_checked(client, url)
            except Exception as exc:  # garde-fou : jamais d'exception propagée
                result = {
                    "http_detected": False,
                    "status": STATUS_UNREACHABLE,
                    "error": str(exc)[:200] or exc.__class__.__name__,
                    "url": url,
                }
            if result.get("http_detected"):
                result["port"] = port
                result["scheme"] = scheme
                return result
            # Mémoriser la meilleure erreur : un échec TLS est plus parlant
            # qu'un simple refus de connexion pour signaler le problème.
            if best_error is None or (
                result.get("status") == STATUS_TLS_UNTRUSTED
                and best_error.get("status") != STATUS_TLS_UNTRUSTED
            ):
                best_error = result

        best_error = best_error or {
            "http_detected": False,
            "status": STATUS_UNREACHABLE,
            "error": "aucune réponse",
            "url": None,
        }
        best_error["port"] = port
        return best_error

    @staticmethod
    def _best_port_result(results: List[dict], port_order: List[int]) -> dict:
        def key(item: dict) -> tuple:
            status = item.get("status", STATUS_UNREACHABLE)
            port = item.get("port", 0)
            port_rank = port_order.index(port) if port in port_order else len(port_order)
            return (_STATUS_PREFERENCE.get(status, 9), port_rank)

        return min(results, key=key)

    # ------------------------------------------------------------
    # Entrées publiques
    # ------------------------------------------------------------

    async def probe_asset(self, ip: str, asset_type: Optional[str]) -> dict:
        """Détecter l'interface web d'un équipement (cible = son IP inventaire)."""
        base = {
            "checked_at": datetime.now(UTC).isoformat(),
            "ip": ip,
            "url": None,
            "status": None,
            "tcp_open": False,
            "http_detected": False,
            "http_status": None,
            "server": None,
            "www_authenticate": None,
            "redirect_to": None,
            "redirect_blocked": None,
            "ports_candidate": [],
            "ports_open": [],
            "error": None,
        }

        try:
            address = ipaddress.ip_address(str(ip).strip())
        except (ValueError, TypeError):
            base["status"] = STATUS_TO_CHECK
            base["error"] = "adresse IP absente ou invalide"
            return base

        allowed, reason = await self.is_host_allowed(str(address))
        if not allowed:
            base["status"] = STATUS_TO_CHECK
            base["error"] = f"cible refusée : {reason}"
            return base

        ports = self.candidate_ports(asset_type)
        base["ports_candidate"] = ports

        async with self._semaphore:
            open_flags = await asyncio.gather(
                *(self._tcp_open(str(address), port) for port in ports)
            )
            open_ports = [port for port, is_open in zip(ports, open_flags) if is_open]
            base["ports_open"] = open_ports
            base["tcp_open"] = bool(open_ports)

            if not open_ports:
                base["status"] = STATUS_UNREACHABLE
                base["error"] = "aucun port ouvert"
                return base

            timeout = httpx.Timeout(self._http_timeout, connect=self._tcp_timeout)
            async with httpx.AsyncClient(
                verify=self.verify,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                results = await asyncio.gather(
                    *(self._probe_port(client, str(address), port) for port in open_ports)
                )

        best = self._best_port_result(list(results), open_ports)
        base.update({
            key: best.get(key)
            for key in (
                "status", "url", "http_detected", "http_status", "server",
                "www_authenticate", "redirect_to", "redirect_blocked", "error",
            )
        })
        base["port"] = best.get("port")
        base["scheme"] = best.get("scheme")
        if best.get("redirect_error") and not base.get("error"):
            base["redirect_error"] = best.get("redirect_error")
        return base

    async def probe_url(self, url: str) -> dict:
        """Tester une URL de gestion existante (sans jamais modifier la cible)."""
        base = {
            "checked_at": datetime.now(UTC).isoformat(),
            "url": None,
            "status": STATUS_UNREACHABLE,
            "http_detected": False,
            "http_status": None,
            "server": None,
            "www_authenticate": None,
            "redirect_to": None,
            "redirect_blocked": None,
            "error": None,
        }

        parsed = urlsplit(url or "")
        if parsed.scheme not in ("http", "https"):
            base["error"] = "schéma refusé (http ou https uniquement)"
            return base
        if parsed.username or parsed.password:
            base["error"] = "identifiants refusés dans l'URL"
            return base
        if not parsed.hostname:
            base["error"] = "hôte absent dans l'URL"
            return base

        allowed, reason = await self.is_host_allowed(parsed.hostname)
        if not allowed:
            base["error"] = f"cible refusée : {reason}"
            return base

        timeout = httpx.Timeout(self._http_timeout, connect=self._tcp_timeout)
        async with httpx.AsyncClient(
            verify=self.verify,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            result = await self._get_checked(client, url)

        base.update({
            key: result.get(key, base.get(key))
            for key in base.keys()
        })
        base["url"] = result.get("url") or url
        return base
