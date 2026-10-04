"""Stockage des fichiers photos (abstraction backend).

Deux couches distinctes :

- les **originaux** (source de vérité) sont gérés par un
  ``PhotoStorageBackend`` — ``LocalFilesystemStorage`` (comportement
  historique) ou ``NasFilesystemStorage`` (répertoire monté, ex.
  ``/mnt/synology/photos`` monté par le système — ForgeAI ne gère ni SMB
  ni NFS) ;
- les **miniatures** et les **versions retouchées** restent toujours sur
  le volume applicatif local (cache rapide, indépendant du NAS).

Arborescence locale sous ``PHOTO_STORAGE_PATH`` (les chemins stockés en
base sont toujours relatifs) :

    originals/<owner_id>/<yyyy>/<mm>/<uuid>.<ext>   # jamais modifié
    thumbs/<photo_id>/<size>.jpg                    # miniatures
    edits/<photo_id>/<uuid>.<jpg|png>               # versions dérivées

Le reste de ForgeAI ne connaît que la façade ``PhotoStorage`` : aucun
chemin NAS n'apparaît dans les services, l'API ou le frontend. En mode
NAS, les originaux restent **immuables** et ne sont **jamais supprimés**
par ForgeAI (``delete_original`` y est un no-op explicite).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Chemin relatif : pas d'absolu, pas de « .. », pas de anti-slash, pas de
# caractères de contrôle. Les espaces et accents (photothèques réelles,
# NAS) sont acceptés.
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class PhotoStorageError(Exception):
    pass


@dataclass(frozen=True)
class StorageStatus:
    """État d'un stockage : ``available`` | ``unavailable`` | ``error``."""

    state: str
    path: str
    detail: str


def check_storage_root(path: Path, *, expect_mount: bool = False) -> StorageStatus:
    """Vérifie qu'un répertoire de stockage est utilisable.

    - absent / pas un répertoire / illisible → ``unavailable`` / ``error`` ;
    - répertoire vide alors qu'un montage est attendu (backend NAS) →
      ``unavailable`` : c'est le cas typique du point de montage qui a
      disparu. Un ``unavailable`` doit **toujours** empêcher tout
      traitement destructif (jamais de suppression massive).
    """
    raw = str(path)
    if not path.exists():
        return StorageStatus(
            "unavailable", raw, "répertoire absent — point de montage non monté ?"
        )
    if not path.is_dir():
        return StorageStatus("error", raw, "le chemin configuré n'est pas un répertoire")
    if not os.access(path, os.R_OK | os.X_OK):
        return StorageStatus("error", raw, "répertoire illisible (droits manquants)")
    if expect_mount:
        try:
            empty = next(path.iterdir(), None) is None
        except OSError as exc:
            return StorageStatus("unavailable", raw, f"répertoire inaccessible: {exc}")
        if empty:
            return StorageStatus(
                "unavailable",
                raw,
                "répertoire vide alors qu'un montage est attendu — montage absent ?",
            )
    return StorageStatus("available", raw, "accessible")


class PhotoStorageBackend(ABC):
    """Contrat d'un stockage d'originaux."""

    name: str

    @property
    @abstractmethod
    def scan_root(self) -> Path:
        """Racine parcourue par le scan V3 (dossier des originaux)."""

    @abstractmethod
    def original_path(self, rel: str) -> Path:
        """Chemin absolu d'un original (``rel`` validé)."""

    @abstractmethod
    def save_original(self, owner_id: int, photo_uuid: str, ext: str, data: bytes) -> str:
        """Écrit un original, retourne le chemin relatif."""

    @abstractmethod
    def delete_original(self, rel: str) -> None:
        """Suppression d'un original échoué — voir les implémentations."""

    @abstractmethod
    def check(self) -> StorageStatus:
        """État du stockage (logs inclus)."""


class LocalFilesystemStorage(PhotoStorageBackend):
    """Stockage local (comportement historique, inchangé)."""

    name = "local"

    def __init__(self, root: Path) -> None:
        self.originals_root = root / "originals"

    @property
    def scan_root(self) -> Path:
        return self.originals_root

    @staticmethod
    def _check_rel(rel: str) -> None:
        check_rel(rel)

    def original_path(self, rel: str) -> Path:
        self._check_rel(rel)
        return self.originals_root / rel

    def save_original(self, owner_id: int, photo_uuid: str, ext: str, data: bytes) -> str:
        rel = original_rel(owner_id, photo_uuid, ext)
        path = self.original_path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return rel

    def delete_original(self, rel: str) -> None:
        path = self.original_path(rel)
        if path.is_file():
            path.unlink()

    def check(self) -> StorageStatus:
        # Nouvelle installation : le dossier n'apparaît qu'au premier
        # import. Le créer (vide, non détruit) évite un faux « indisponible ».
        if not self.originals_root.exists():
            try:
                self.originals_root.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        status = check_storage_root(self.originals_root, expect_mount=False)
        _log_status("local", status)
        return status


class NasFilesystemStorage(PhotoStorageBackend):
    """Originaux sur un répertoire monté (NAS Synology, monté par le système).

    ForgeAI n'ouvre aucune connexion réseau : seul le chemin monté est
    utilisé. **Aucune suppression** d'original n'est jamais effectuée sur
    ce backend (``delete_original`` est un no-op) — la source de vérité
    NAS reste intacte, y compris en cas de photo supprimée dans ForgeAI.
    """

    name = "nas"

    def __init__(self, nas_path: str) -> None:
        if not (nas_path or "").strip():
            raise PhotoStorageError("PHOTO_NAS_PATH manquant pour le backend NAS")
        self.nas_root = Path(nas_path).expanduser()

    @property
    def scan_root(self) -> Path:
        return self.nas_root

    @staticmethod
    def _check_rel(rel: str) -> None:
        check_rel(rel)

    def original_path(self, rel: str) -> Path:
        self._check_rel(rel)
        return self.nas_root / rel

    def save_original(self, owner_id: int, photo_uuid: str, ext: str, data: bytes) -> str:
        rel = original_rel(owner_id, photo_uuid, ext)
        path = self.original_path(rel)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise PhotoStorageError(
                f"Écriture NAS impossible (montage lecture seule ?): {exc}"
            ) from exc
        return rel

    def delete_original(self, rel: str) -> None:
        # Règle V3 : jamais de suppression d'original NAS, même sur un
        # échec d'import (l'écriture reste sur le volume NAS uniquement si
        # elle a eu lieu ; on laisse l'original en place).
        logger.warning(
            "[PHOTO-STORAGE] suppression d'original NAS ignorée (rel=%s)", rel
        )

    def check(self) -> StorageStatus:
        status = check_storage_root(self.nas_root, expect_mount=True)
        _log_status("nas", status)
        return status


def _log_status(backend: str, status: StorageStatus) -> None:
    level = logging.INFO if status.state == "available" else logging.WARNING
    logger.log(
        level,
        "[PHOTO-STORAGE] backend=%s état=%s chemin=%s (%s)",
        backend,
        status.state,
        status.path,
        status.detail,
    )


def check_rel(rel: str) -> None:
    """Valide un chemin relatif d'original (anti path traversal)."""
    if not rel or not isinstance(rel, str):
        raise PhotoStorageError(f"Chemin de fichier invalide: {rel!r}")
    if rel.startswith("/") or "\\" in rel or _CTRL.search(rel):
        raise PhotoStorageError(f"Chemin de fichier invalide: {rel!r}")
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PhotoStorageError(f"Chemin de fichier invalide: {rel!r}")


def original_rel(owner_id: int, photo_uuid: str, ext: str) -> str:
    from datetime import datetime

    now = datetime.now()
    return f"{owner_id}/{now.year:04d}/{now.month:02d}/{photo_uuid}{ext}"


def hash_file(path: Path, chunk_size: int = 1 << 16) -> str:
    """SHA-256 streamé d'un fichier (mémoire bornée, gros volumes NAS)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class PhotoStorage:
    """Façade du stockage — seule porte d'entrée du reste de ForgeAI.

    Miniatures et retouches : toujours locales. Originaux : délégués au
    backend courant (ou au backend propre à une photo via
    ``original_path(rel, backend=...)``).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.root = Path(settings.PHOTO_STORAGE_PATH).expanduser()
        thumb_setting = (settings.PHOTO_THUMBNAIL_PATH or "").strip()
        self.thumbs_root = (
            Path(thumb_setting).expanduser() if thumb_setting else self.root / "thumbs"
        )
        self.originals_root = self.root / "originals"
        self.edits_root = self.root / "edits"
        self.default_backend_name = (settings.PHOTO_STORAGE_BACKEND or "local").strip()
        self._backends: dict[str, PhotoStorageBackend] = {
            "local": LocalFilesystemStorage(self.root),
        }
        nas_path = (settings.PHOTO_NAS_PATH or "").strip()
        if nas_path:
            self._backends["nas"] = NasFilesystemStorage(nas_path)

    # ------------------------------------------------------------------ util
    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _check_rel(rel: str) -> None:
        check_rel(rel)

    @staticmethod
    def _unique_path(directory: Path, filename: str) -> Path:
        candidate = directory / filename
        stem, suffix = candidate.stem, candidate.suffix
        index = 1
        while candidate.exists():
            candidate = directory / f"{stem}-{index}{suffix}"
            index += 1
        return candidate

    # ---------------------------------------------------------------- backends
    def backend(self, name: str | None = None) -> PhotoStorageBackend:
        """Backend par nom (défaut : backend courant de la configuration)."""
        key = (name or self.default_backend_name or "local").strip()
        backend = self._backends.get(key)
        if backend is None:
            raise PhotoStorageError(f"Backend de stockage inconnu: {key!r}")
        return backend

    def backend_for_photo(self, photo) -> PhotoStorageBackend:
        """Backend d'une photo (colonne ``storage_backend``)."""
        return self.backend(getattr(photo, "storage_backend", None) or None)

    def available_backends(self) -> list[str]:
        return sorted(self._backends)

    def check(self, backend_name: str | None = None) -> StorageStatus:
        return self.backend(backend_name).check()

    # ------------------------------------------------------------- originaux
    def original_rel(self, owner_id: int, photo_uuid: str, ext: str) -> str:
        return original_rel(owner_id, photo_uuid, ext)

    def original_path(self, rel: str, backend: str | None = None) -> Path:
        return self.backend(backend).original_path(rel)

    def save_original(
        self, owner_id: int, photo_uuid: str, ext: str, data: bytes, backend: str | None = None
    ) -> str:
        return self.backend(backend).save_original(owner_id, photo_uuid, ext, data)

    def delete_original(self, rel: str, backend: str | None = None) -> None:
        self.backend(backend).delete_original(rel)

    # ------------------------------------------------------------ miniatures
    def thumbnail_rel(self, photo_id: int, size: str) -> str:
        return f"{photo_id}/{size}.jpg"

    def thumbnail_path(self, rel: str) -> Path:
        self._check_rel(rel)
        return self.thumbs_root / rel

    # ---------------------------------------------------------------- versions
    def edit_rel(self, photo_id: int, edit_uuid: str, ext: str = ".jpg") -> str:
        return f"{photo_id}/{edit_uuid}{ext}"

    def edit_path(self, rel: str) -> Path:
        self._check_rel(rel)
        return self.edits_root / rel

    # ---------------------------------------------------------------- purge
    def delete_thumbnails(self, photo_id: int) -> None:
        directory = self.thumbs_root / str(photo_id)
        if directory.is_dir():
            shutil.rmtree(directory, ignore_errors=True)

    def delete_edits(self, photo_id: int) -> None:
        directory = self.edits_root / str(photo_id)
        if directory.is_dir():
            shutil.rmtree(directory, ignore_errors=True)


_storage: PhotoStorage | None = None


def get_photo_storage() -> PhotoStorage:
    global _storage
    if _storage is None:
        _storage = PhotoStorage()
    return _storage
