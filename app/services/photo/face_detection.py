"""Détection de visages (local-first, jamais sur l'original).

Le pipeline ne connaît que le protocol ``FaceDetectionProvider`` (name,
model, version, dimensions + ``detect``) : le détecteur travaille sur la
miniature configurée (``PHOTO_ANALYSIS_THUMB_SIZE``), ne modifie jamais
l'original, et produit les boîtes englobantes normalisées, la confidence
et l'embedding facial.

Implémentation initiale : ``LocalFaceDetector`` — heuristique pure
Python/Pillow (segmentation « teinte de peau » + composantes connexes),
déterministe, 100 % locale, aucune dépendance ni appel réseau. Un moteur
réel (Haar, DNN, …) pourra être enregistré dans le registre sans changer
ni les jobs ni les tables : ``detector`` / ``model`` / ``version`` sont
stockés sur chaque visage et dans l'état ``photo_analyses`` (kind
« faces »), ce qui déclenche la ré-indexation quand ils changent.

Confidentialité : aucun embedding facial ne quitte le serveur (le
détecteur par défaut est local ; aucun provider externe n'est branché).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoAnalysis, PhotoFace, PhotoPerson
from app.services.photo.analysis import resolve_analysis_image
from app.services.photo.embeddings import l2_normalize

logger = logging.getLogger(__name__)

# Nombre maximal de visages retenus par photo (protection des extrêmes).
MAX_FACES_PER_PHOTO = 8

# Côté de l'image de travail (le décodage pleine taille ne sert qu'au
# recadrage de l'embedding) : vitesse + réduction du bruit.
_WORK_MAX_SIDE = 160


@dataclass
class DetectedFace:
    """Résultat brut d'une détection : boîte normalisée (0..1) + embedding."""

    x: float
    y: float
    w: float
    h: float
    confidence: float
    embedding: list[float] | None = None


class FaceDetectionProvider(Protocol):
    """Contrat d'un moteur de détection de visages."""

    name: str
    model: str
    version: int
    dimensions: int

    async def detect(self, image_path: Path) -> list[DetectedFace]:
        """Détecte 0, 1 ou plusieurs visages. Lecture seule."""
        ...


def _is_skin(r: int, g: int, b: int) -> bool:
    """Règle classique R-G-B (déterministe, sans modèle)."""
    return (
        r > 95
        and g > 40
        and b > 20
        and max(r, g, b) - min(r, g, b) > 15
        and abs(r - g) > 15
        and r > g
        and r > b
    )


def _connected_components(
    mask: bytearray, width: int, height: int
) -> list[tuple[int, int, int, int, int]]:
    """Composantes connexes 4-voisins (parcours itératif, pas de récursion).

    Retourne les bounding boxes ``(x0, y0, x1, y1, aire)`` des blobs.
    """
    boxes: list[tuple[int, int, int, int, int]] = []
    seen = bytearray(width * height)
    stack: list[int] = []
    for start in range(width * height):
        if not mask[start] or seen[start]:
            continue
        # Nouveau blob.
        stack.append(start)
        seen[start] = 1
        x0 = x1 = start % width
        y0 = y1 = start // width
        area = 0
        while stack:
            index = stack.pop()
            area += 1
            x = index % width
            y = index // width
            if x < x0:
                x0 = x
            if x > x1:
                x1 = x
            if y < y0:
                y0 = y
            if y > y1:
                y1 = y
            if x > 0 and mask[index - 1] and not seen[index - 1]:
                seen[index - 1] = 1
                stack.append(index - 1)
            if x + 1 < width and mask[index + 1] and not seen[index + 1]:
                seen[index + 1] = 1
                stack.append(index + 1)
            if y >= width and mask[index - width] and not seen[index - width]:
                seen[index - width] = 1
                stack.append(index - width)
            if y + 1 < height and mask[index + width] and not seen[index + width]:
                seen[index + width] = 1
                stack.append(index + width)
        boxes.append((x0, y0, x1, y1, area))
    return boxes


class LocalFaceDetector:
    """Détecteur local par blobs « teinte de peau ».

    Pipeline : miniature → masque peau → composantes connexes → filtres
    (taille, proportion) → embedding = vignette 8×8 RGB du rectangle
    recadré (192 dims, normalisée L2). Local, déterministe, aucune
    dépendance ni modèle externe — point de départ remplaçable.
    """

    name = "local_heuristic"
    model = "skin-blob-v1"
    version = 1
    dimensions = 8 * 8 * 3

    async def detect(self, image_path: Path) -> list[DetectedFace]:
        return await asyncio.to_thread(self._detect_sync, image_path)

    def _detect_sync(self, image_path: Path) -> list[DetectedFace]:
        from PIL import Image, ImageOps

        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            work = image
            if max(work.size) > _WORK_MAX_SIDE:
                ratio = _WORK_MAX_SIDE / max(work.size)
                work = work.resize(
                    (max(1, int(work.width * ratio)), max(1, int(work.height * ratio))),
                    Image.Resampling.BOX,
                )
            width, height = work.size
            data = list(work.tobytes())  # RGB, 3 octets/pixel (pas de getdata).

            mask = bytearray(width * height)
            for index in range(width * height):
                offset = index * 3
                if _is_skin(data[offset], data[offset + 1], data[offset + 2]):
                    mask[index] = 1

            min_area = max(16, int(width * height * 0.0015))
            max_box_area = int(width * height * 0.6)
            candidates = []
            for x0, y0, x1, y1, area in _connected_components(mask, width, height):
                box_w = x1 - x0 + 1
                box_h = y1 - y0 + 1
                if area < min_area or box_w * box_h > max_box_area:
                    continue
                if box_w < 4 or box_h < 4:
                    continue
                ratio = box_w / box_h
                if ratio < 0.3 or ratio > 3.3:
                    continue
                candidates.append((area, x0, y0, x1, y1, box_w, box_h))
            # Tri déterministe (aire décroissante, puis position).
            candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
            candidates = candidates[:MAX_FACES_PER_PHOTO]

            scale_x = image.width / width
            scale_y = image.height / height
            faces: list[DetectedFace] = []
            for area, x0, y0, _x1, _y1, box_w, box_h in candidates:
                fill = area / float(box_w * box_h)
                size_score = min(1.0, area / (width * height * 0.02))
                confidence = round(min(0.99, 0.35 + 0.45 * fill + 0.25 * size_score), 3)
                # Recadrage pleine résolution pour l'embedding.
                crop = image.crop(
                    (
                        int(x0 * scale_x),
                        int(y0 * scale_y),
                        min(image.width, int((x0 + box_w) * scale_x)),
                        min(image.height, int((y0 + box_h) * scale_y)),
                    )
                )
                grid = crop.resize((8, 8), Image.Resampling.BOX)
                vector = l2_normalize(
                    [channel / 255.0 for channel in grid.tobytes()]
                )
                faces.append(
                    DetectedFace(
                        x=round(x0 / width, 6),
                        y=round(y0 / height, 6),
                        w=round(box_w / width, 6),
                        h=round(box_h / height, 6),
                        confidence=confidence,
                        embedding=vector,
                    )
                )
        return faces


_DETECTORS: dict[str, FaceDetectionProvider] = {
    LocalFaceDetector.name: LocalFaceDetector(),
}


def register_face_detector(provider: FaceDetectionProvider) -> None:
    """Enregistre (ou remplace) un détecteur — utilisé par les tests et
    par les futurs moteurs."""
    _DETECTORS[provider.name] = provider


def get_face_detector(name: str | None = None) -> FaceDetectionProvider:
    configured = name or get_settings().PHOTO_FACE_DETECTOR
    return (
        _DETECTORS.get(configured)
        or _DETECTORS.get(LocalFaceDetector.name)
        or next(iter(_DETECTORS.values()))
    )


def faces_up_to_date(state: PhotoAnalysis | None, provider: FaceDetectionProvider) -> bool:
    """True si l'état de détection correspond au détecteur courant."""
    if state is None or state.status != "done":
        return False
    return (
        state.provider == provider.name
        and state.model == provider.model
        and state.version == provider.version
    )


async def _clear_covers_referencing(db: AsyncSession, face_ids: set[int]) -> None:
    """Annule les couvertures pointant vers des visages sur le point d'être supprimés."""
    if not face_ids:
        return
    result = await db.execute(
        select(PhotoPerson).where(PhotoPerson.cover_face_id.in_(face_ids))
    )
    for person in result.scalars().all():
        person.cover_face_id = None


async def run_face_detection(
    db: AsyncSession, photo: Photo, *, force: bool = False
) -> PhotoAnalysis:
    """Détecte les visages de ``photo`` et persiste l'état (kind « faces »).

    Une seule ligne ``photo_analyses`` (kind="faces") sert d'état
    versionné : provider / model / version / status / error, exactement
    comme l'analyse de classification. Les anciens visages de la photo
    sont remplacés (les couvertures qui les referençaient sont neutralisées).
    Toute erreur est consignée puis re-lancée : c'est le job qui applique
    le retry (backoff, max_attempts).
    """
    provider = get_face_detector()

    state = (
        await db.execute(
            select(PhotoAnalysis).where(
                PhotoAnalysis.photo_id == photo.id,
                PhotoAnalysis.kind == "faces",
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = PhotoAnalysis(photo_id=photo.id, kind="faces", status="pending")
        db.add(state)
    if not force and faces_up_to_date(state, provider):
        return state

    state.status = "running"
    state.provider = provider.name
    state.model = provider.model
    state.version = provider.version
    state.error = None
    await db.commit()
    state_id = state.id

    try:
        # Savepoint : seule la détection est annulée en cas d'échec. Pas de
        # rollback global — il expirerait les objets de la session (dont le
        # job en cours de traitement) et casserait la boucle de jobs.
        async with db.begin_nested():
            image_path = await resolve_analysis_image(db, photo)
            detections = await provider.detect(image_path)

            old_faces = (
                await db.execute(select(PhotoFace).where(PhotoFace.photo_id == photo.id))
            ).scalars().all()
            old_ids = {face.id for face in old_faces}
            await _clear_covers_referencing(db, old_ids)
            for face in old_faces:
                await db.delete(face)
            # Flush avant les INSERT : SQLA émet d'abord les DELETE, la clé
            # étrangère reste satisfaisante et aucune contrainte n'est violée.
            await db.flush()

            for detection in detections[:MAX_FACES_PER_PHOTO]:
                db.add(
                    PhotoFace(
                        photo_id=photo.id,
                        x=detection.x,
                        y=detection.y,
                        w=detection.w,
                        h=detection.h,
                        confidence=detection.confidence,
                        detector=provider.name,
                        model=provider.model,
                        version=provider.version,
                        embedding_json=detection.embedding,
                    )
                )

            state.status = "done"
            state.result_json = {"faces": len(detections[:MAX_FACES_PER_PHOTO])}
            state.completed_at = datetime.now(UTC).replace(tzinfo=None)
            state.error = None
        await db.commit()
        logger.info(
            "[PHOTO-FACE] photo=%s détecteur=%s model=%s v%s visages=%s",
            photo.id,
            provider.name,
            provider.model,
            provider.version,
            len(detections[:MAX_FACES_PER_PHOTO]),
        )
    except Exception as exc:
        # L'état est (peut-être) expiré par l'annulation du savepoint : on le
        # recharge avant d'écrire l'échec — la session reste intacte.
        state = (
            await db.execute(
                select(PhotoAnalysis).where(PhotoAnalysis.id == state_id)
            )
        ).scalar_one()
        state.status = "failed"
        state.error = f"{type(exc).__name__}: {exc}"
        await db.commit()
        raise
    return state
