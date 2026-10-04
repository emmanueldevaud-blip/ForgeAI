"""Regroupement automatique des visages (local-first).

Stratégie : comparaison aux **centroïdes** des groupes, pas d'all-vs-all
sur les visages — O(n·k) avec k ≈ nombre de groupes (dizaines au plus),
et non O(n²) avec plusieurs milliers de photos.

Le ``FaceIndex`` abstracte la recherche top-k : l'implémentation
``FlatFaceIndex`` fait de la force brute sur les centroïdes (exacte et
suffisante à l'échelle d'une photothèque personnelle) ; un vrai index
vectoriel (FAISS, MySQL VECTOR…) pourra être branché ici sans changer
l'algorithme de regroupement.

Règles d'identité :
- le regroupement ne crée que des groupes anonymes (« Personne 1 »…) et
  ne rejoint que des groupes anonymes — jamais un groupe déjà nommé par
  l'utilisateur (on n'affirme pas qui est quelqu'un) ;
- les fusions automatiques portent aussi uniquement sur les groupes
  anonymes ; fusion / renommage / séparation restent des actions
  explicites de l'utilisateur (API « Personnes »).

Confidentialité : tout est calculé dans la session applicative, scopé au
propriétaire ; aucun embedding n'est transmis à l'extérieur.
"""

from __future__ import annotations

import logging
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoFace, PhotoPerson
from app.services.photo.embeddings import cosine_similarity, l2_normalize

logger = logging.getLogger(__name__)

_AUTO_NAME_RE = re.compile(r"^Personne (\d+)$")

# Itérations max de fusion pair-à-pair (borné : chaque fusion réduit k).
_MAX_MERGE_ROUNDS = 10


class FlatFaceIndex:
    """Index de vecteurs par personne (similarité cosinus).

    Force brute mais uniquement sur les centroïdes de groupes — voir le
    module docstring. L'interface (upsert / remove / search) est celle
    d'un index vectoriel « vrai » : remplacer la classe suffit.
    """

    def __init__(self, entries: dict[int, list[float]] | None = None):
        self._entries: dict[int, list[float]] = dict(entries or {})

    def upsert(self, person_id: int, vector: list[float]) -> None:
        self._entries[person_id] = vector

    def remove(self, person_id: int) -> None:
        self._entries.pop(person_id, None)

    def search(
        self, vector: list[float], *, threshold: float
    ) -> tuple[int, float] | None:
        """Groupe le plus proche ≥ threshold (person_id la plus basse en cas d'égalité)."""
        best: tuple[int, float] | None = None
        for person_id in sorted(self._entries):
            score = cosine_similarity(vector, self._entries[person_id])
            if score >= threshold and (best is None or score > best[1]):
                best = (person_id, score)
        return best


def _centroid(vectors: list[list[float]]) -> list[float]:
    """Moyenne des vecteurs (déjà normalisés), re-normalisée L2."""
    if not vectors:
        return []
    dimensions = len(vectors[0])
    mean = [0.0] * dimensions
    for vector in vectors:
        for index, value in enumerate(vector):
            mean[index] += value
    count = float(len(vectors))
    return l2_normalize([value / count for value in mean])


def is_auto_name(name: str | None) -> bool:
    """True si le nom est un nom auto généré (« Personne 4 »)."""
    return bool(name and _AUTO_NAME_RE.match(name))


def next_auto_name(taken: set[str]) -> str:
    """« Personne N » avec N = max(utilisés) + 1 (déterministe, unique)."""
    highest = 0
    for name in taken:
        match = _AUTO_NAME_RE.match(name or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"Personne {highest + 1}"


async def cleanup_empty_auto_people(db: AsyncSession, owner_id: int) -> int:
    """Supprime les groupes anonymes devenus vieux zéro visage.

    Les groupes nommés par l'utilisateur sont toujours conservés (sauf
    action explicite de sa part).
    """
    result = await db.execute(
        select(PhotoPerson).where(PhotoPerson.owner_id == owner_id)
    )
    removed = 0
    for person in result.scalars().all():
        if not is_auto_name(person.name):
            continue
        remaining = (
            await db.execute(
                select(PhotoFace.id).where(PhotoFace.person_id == person.id).limit(1)
            )
        ).first()
        if remaining is None:
            await db.delete(person)
            removed += 1
    return removed


async def group_owner_faces(db: AsyncSession, owner_id: int) -> dict[str, int]:
    """Regroupe les visages non affectés du propriétaire en groupes anonymes.

    - les visages déjà affectés (groupe anonyme ou nommé) servent
      d'ancres ; ils ne bougent jamais automatiquement ;
    - un visage non affecté rejoint le groupe anonyme le plus proche
      (cosinus ≥ ``PHOTO_FACE_GROUP_THRESHOLD``) ou crée « Personne N » ;
    - les groupes anonymes suffisamment proches (≥
      ``PHOTO_FACE_GROUP_MERGE_THRESHOLD``) sont fusionnés ;
    - la couverture manquante de chaque groupe est renseignée.

    Retourne des compteurs de journalisation (assigned / created / merged).
    """
    settings = get_settings()
    if not settings.PHOTO_FACE_GROUPING_ENABLED:
        return {"assigned": 0, "created": 0, "merged": 0}

    faces = (
        await db.execute(
            select(PhotoFace)
            .join(Photo, Photo.id == PhotoFace.photo_id)
            .where(
                Photo.owner_id == owner_id,
                Photo.is_deleted.is_(False),
                PhotoFace.embedding_json.is_not(None),
            )
            .order_by(PhotoFace.id)
        )
    ).scalars().all()
    if not faces:
        return {"assigned": 0, "created": 0, "merged": 0}

    persons = (
        await db.execute(
            select(PhotoPerson)
            .where(PhotoPerson.owner_id == owner_id)
            .order_by(PhotoPerson.id)
        )
    ).scalars().all()
    person_by_id = {person.id: person for person in persons}
    anonymous_ids = {p.id for p in persons if is_auto_name(p.name)}
    taken_names = {person.name for person in persons}

    vectors_by_person: dict[int, list[list[float]]] = {}
    for face in faces:
        if face.person_id in person_by_id:
            vectors_by_person.setdefault(face.person_id, []).append(
                list(face.embedding_json)
            )

    # Seuls les groupes anonymes sont des cibles automatiques.
    index = FlatFaceIndex(
        {
            person_id: _centroid(vectors)
            for person_id, vectors in vectors_by_person.items()
            if person_id in anonymous_ids
        }
    )

    assigned = 0
    created = 0
    for face in faces:
        if face.person_id is not None:
            continue
        vector = list(face.embedding_json)
        match = index.search(
            vector, threshold=settings.PHOTO_FACE_GROUP_THRESHOLD
        )
        if match is not None:
            face.person_id = match[0]
            vectors_by_person.setdefault(match[0], []).append(vector)
            index.upsert(match[0], _centroid(vectors_by_person[match[0]]))
            assigned += 1
        else:
            person = PhotoPerson(
                owner_id=owner_id, name=next_auto_name(taken_names)
            )
            db.add(person)
            await db.flush()
            taken_names.add(person.name)
            anonymous_ids.add(person.id)
            person_by_id[person.id] = person
            face.person_id = person.id
            vectors_by_person[person.id] = [vector]
            index.upsert(person.id, _centroid([vector]))
            created += 1

    # Fusion des groupes anonymes (paires, k² sur des dizaines d'entrées).
    merged = 0
    for _round in range(_MAX_MERGE_ROUNDS):
        changed = False
        anon_ids = sorted(
            person_id
            for person_id in vectors_by_person
            if person_id in anonymous_ids
        )
        for position, id_a in enumerate(anon_ids):
            for id_b in anon_ids[position + 1:]:
                similarity = cosine_similarity(
                    _centroid(vectors_by_person[id_a]),
                    _centroid(vectors_by_person[id_b]),
                )
                if similarity < settings.PHOTO_FACE_GROUP_MERGE_THRESHOLD:
                    continue
                # id_b → id_a (ordre déterministe : le plus ancien survive).
                source_faces = (
                    await db.execute(
                        select(PhotoFace).where(PhotoFace.person_id == id_b)
                    )
                ).scalars().all()
                for face in source_faces:
                    face.person_id = id_a
                # Flush avant le DELETE de la source : sinon SQLAlchemy
                # rechargerait ces visages comme enfants de la source et
                # remettrait person_id à NULL (désassociation par défaut).
                await db.flush()
                vectors_by_person[id_a].extend(vectors_by_person.pop(id_b))
                anonymous_ids.discard(id_b)
                index.remove(id_b)
                index.upsert(id_a, _centroid(vectors_by_person[id_a]))
                source = person_by_id.pop(id_b, None)
                if source is not None:
                    taken_names.discard(source.name)
                    await db.delete(source)
                merged += 1
                changed = True
                break
            if changed:
                break
        if not changed:
            break

    # Couverture manquante : premier visage (id minimal) du groupe.
    for person_id, vectors in vectors_by_person.items():
        person = person_by_id.get(person_id)
        if person is None or person.cover_face_id is not None:
            continue
        first_face = (
            await db.execute(
                select(PhotoFace.id)
                .where(PhotoFace.person_id == person_id)
                .order_by(PhotoFace.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if first_face is not None:
            person.cover_face_id = first_face

    await db.commit()
    logger.info(
        "[PHOTO-FACE] regroupement owner=%s assignés=%s créés=%s fusionnés=%s",
        owner_id,
        assigned,
        created,
        merged,
    )
    return {"assigned": assigned, "created": created, "merged": merged}
