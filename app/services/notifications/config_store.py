"""Configuration des notifications Web Push (clés VAPID).

Stockage : table ``module_configs`` (module « sport »), sur le même mécanisme
que la configuration IA / SMTP. Les valeurs DB font foi sur l'environnement ;
l'overlay est appliqué à chaud sur l'instance ``Settings`` partagée, donc
aucun redémarrage après génération ou modification.

La clé privée n'est jamais renvoyée au frontend : seules la clé publique
(déjà destinée aux navigateurs) et le sujet ressortent via l'API.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.module import Module, ModuleConfig
from app.services.ai_gateway.config_store import apply_from_db, db_key
from app.services.notification import _load_vapid_private_key

VAPID_SETTINGS_FIELDS: tuple[str, ...] = (
    "NOTIFICATION_VAPID_PUBLIC_KEY",
    "NOTIFICATION_VAPID_PRIVATE_KEY",
    "NOTIFICATION_VAPID_SUBJECT",
)
SECRET_FIELDS = frozenset({"NOTIFICATION_VAPID_PRIVATE_KEY"})
MODULE_CODE = "sport"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_vapid_keys() -> tuple[str, str]:
    """Nouvelle paire P-256 : (clé publique, clé privée) en base64url."""
    key = ec.generate_private_key(ec.SECP256R1())
    public = _b64url(
        key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    private = _b64url(key.private_numbers().private_value.to_bytes(32, "big"))
    return public, private


def derive_public_key(private_key: str) -> str:
    """Clé publique (base64url) correspondant à une clé privée fournie.

    Valide la clé au passage : PEM, raw 32 octets ou DER sont acceptés
    (même formats que ``_load_vapid_private_key``).
    """
    key = _load_vapid_private_key(private_key)
    return _b64url(
        key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )


def _validate_subject(subject: str) -> str:
    subject = subject.strip()
    if subject and not (subject.startswith("mailto:") or subject.startswith("https://")):
        raise ValueError("Le sujet VAPID doit commencer par « mailto: » ou « https:// »")
    return subject


async def _save_values(db: AsyncSession, values: dict[str, str]) -> None:
    module_result = await db.execute(select(Module).where(Module.code == MODULE_CODE))
    module = module_result.scalar_one_or_none()
    if module is None:
        raise ValueError("Module Sport introuvable")
    configs_result = await db.execute(select(ModuleConfig).where(ModuleConfig.module_id == module.id))
    configs = {config.key: config for config in configs_result.scalars().all()}
    for key, value in values.items():
        config = configs.get(key)
        if config is not None:
            config.value = value
        else:
            db.add(
                ModuleConfig(
                    module_id=module.id,
                    key=key,
                    value=value,
                    is_secret=key in {db_key(field) for field in SECRET_FIELDS},
                )
            )
    await db.commit()
    await apply_from_db(db, VAPID_SETTINGS_FIELDS, MODULE_CODE)


async def vapid_status(db: AsyncSession) -> dict:
    """État courant (recharge l'overlay DB pour refléter la base)."""
    await apply_from_db(db, VAPID_SETTINGS_FIELDS, MODULE_CODE)
    settings = get_settings()
    # VAPID_PUBLIC_KEY est dérivé de la clé privée si absent.
    from app.services.notification import NotificationService

    return {
        "configured": bool(settings.NOTIFICATION_VAPID_PRIVATE_KEY),
        "subject": settings.NOTIFICATION_VAPID_SUBJECT or "",
        "public_key": NotificationService.vapid_public_key(),
    }


async def generate_and_save(db: AsyncSession, default_subject: str | None = None) -> dict:
    """Génère une nouvelle paire de clés, la persiste et l'applique à chaud."""
    public, private = generate_vapid_keys()
    values = {
        db_key("NOTIFICATION_VAPID_PUBLIC_KEY"): public,
        db_key("NOTIFICATION_VAPID_PRIVATE_KEY"): private,
    }
    settings = get_settings()
    subject = settings.NOTIFICATION_VAPID_SUBJECT or default_subject or ""
    if subject:
        values[db_key("NOTIFICATION_VAPID_SUBJECT")] = subject
    await _save_values(db, values)
    return await vapid_status(db)


async def save_vapid(
    db: AsyncSession,
    *,
    private_key: str | None = None,
    subject: str | None = None,
) -> dict:
    """Configure une clé privée existante et/ou le sujet, puis applique."""
    values: dict[str, str] = {}
    if private_key and private_key.strip():
        stripped = private_key.strip()
        values[db_key("NOTIFICATION_VAPID_PRIVATE_KEY")] = stripped
        values[db_key("NOTIFICATION_VAPID_PUBLIC_KEY")] = derive_public_key(stripped)
    if subject is not None:
        values[db_key("NOTIFICATION_VAPID_SUBJECT")] = _validate_subject(subject)
    if not values:
        return await vapid_status(db)
    await _save_values(db, values)
    return await vapid_status(db)


async def apply_vapid_from_db(db: AsyncSession) -> None:
    """Overlay VAPID au démarrage de l'application (même call que l'IA)."""
    await apply_from_db(db, VAPID_SETTINGS_FIELDS, MODULE_CODE)
