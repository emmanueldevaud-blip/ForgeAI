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
propriateur ; aucun embedding n'est transmis à l'extérieur.

Exécution : les visages sont lus par paquets clé-sur-croissante et la
boucle d'événements reprend la main entre chaque paquet — le regroupement
peut porter des centaines de milliers de visages sans geler le serveur
HTTP. Seules les sommes/quantités par groupe sont conservées (mémoire
bornée), les centroïdes en découlent.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections.abc import AsyncIterator
from itertools import zip_longest
from operator import mul
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoFace, PhotoPerson
from app.services.photo.embeddings import l2_normalize

logger = logging.getLogger(__name__)

_AUTO_NAME_RE = re.compile(r"^Personne (\d+)$")

# Itérations max de fusion pair-à-pair (borné : chaque fusion réduit k).
_MAX_MERGE_ROUNDS = 10

# Paquets de lecture / d'écriture : le regroupement ne materialise jamais
# la totalité des visages d'un propriétaire (~150k lignes × embedding) —
# chaque paquet lu rend la main à la boucle d'événements.
_FACE_CHUNK = 100
_UPDATE_CHUNK = 1000

# ``math.sumprod`` (Python 3.12+) est ~6× plus rapide que la boucle ; repli
# portable pour l'image de production (Python 3.11).
_SUMPROD = getattr(math, "sumprod", None)


def _dot(a: list[float], b: list[float]) -> float:
    """Produit scalaire de deux vecteurs (déjà normalisés L2 = cosinus)."""
    if len(a) != len(b) or not a:
        return 0.0
    if _SUMPROD is not None:
        return float(_SUMPROD(a, b))
    return sum(map(mul, a, b))


class FlatFaceIndex:
    """Index de vecteurs par personne (similarité cosinus).

    Force brute mais uniquement sur les centroïdes de groupes — voir le
    module docstring. L'interface (upsert / remove / search) est celle
    d'un index vectoriel « vrai » : remplacer la classe suffit.

    Les vecteurs sont normalisés à l'insertion et l'ordre des ``person_id``
    est trié une seule fois par mutation (et non à chaque recherche) : à
    k groupes, la recherche reste un simple produit scalaire par entrée.
    """

    def __init__(self, entries: dict[int, list[float]] | None = None):
        self._entries: dict[int, list[float]] = {
            person_id: l2_normalize(list(vector))
            for person_id, vector in (entries or {}).items()
        }
        self._order: list[int] = sorted(self._entries)
        self._ordered = True

    def upsert(self, person_id: int, vector: list[float]) -> None:
        self._entries[person_id] = l2_normalize(list(vector))
        self._ordered = False

    def remove(self, person_id: int) -> None:
        self._entries.pop(person_id, None)
        self._ordered = False

    def search(
        self, vector: list[float], *, threshold: float
    ) -> tuple[int, float] | None:
        """Groupe le plus proche ≥ threshold (person_id la plus basse en cas d'égalité)."""
        if not self._ordered:
            self._order = sorted(self._entries)
            self._ordered = True
        if not self._order:
            return None
        query = l2_normalize(list(vector))
        best: tuple[int, float] | None = None
        for person_id in self._order:
            score = _dot(query, self._entries[person_id])
            if score >= threshold and (best is None or score > best[1]):
                best = (person_id, score)
        return best


def _centroid(total: list[float], count: int) -> list[float]:
    """Moyenne des vecteurs (somme portée / effectif), re-normalisée L2.

    Équivalent à la moyenne des vecteurs déjà normalisés : les vecteurs ne
    sont jamais tous conservés en mémoire, seule la somme l'est.
    """
    if not total or count <= 0:
        return []
    return l2_normalize([value / count for value in total])


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


async def _face_chunks(
    db: AsyncSession, owner_id: int, *, assigned: bool
) -> AsyncIterator[list[tuple[int, int | None, list]]]:
    """Itère (face_id, person_id, embedding) par paquets ordonnés par id.

    ``assigned=True`` : visages déjà affectés (ancres).
    ``assigned=False`` : visages non affectés (à regrouper).

    Le clé-sur-croissante (``id > dernier``) permet de lire sans jamais
    charger la table entière, et rend la main à la boucle d'événements
    après chaque paquet : le serveur HTTP reste serv pendant le
    regroupement.
    """
    last_id = 0
    while True:
        rows = (
            await db.execute(
                select(PhotoFace.id, PhotoFace.person_id, PhotoFace.embedding_json)
                .join(Photo, Photo.id == PhotoFace.photo_id)
                .where(
                    Photo.owner_id == owner_id,
                    Photo.is_deleted.is_(False),
                    PhotoFace.embedding_json.is_not(None),
                    (
                        PhotoFace.person_id.is_not(None)
                        if assigned
                        else PhotoFace.person_id.is_(None)
                    ),
                    PhotoFace.id > last_id,
                )
                .order_by(PhotoFace.id)
                .limit(_FACE_CHUNK)
            )
        ).all()
        if not rows:
            return
        last_id = rows[-1][0]
        yield rows
        await asyncio.sleep(0)


async def _move_faces(db: AsyncSession, source_id: int, target_id: int) -> None:
    """Réaffecte en masse les visages d'un groupe vers un autre."""
    last_id = 0
    while True:
        ids = (
            await db.execute(
                select(PhotoFace.id)
                .where(
                    PhotoFace.person_id == source_id,
                    PhotoFace.id > last_id,
                )
                .order_by(PhotoFace.id)
                .limit(_UPDATE_CHUNK)
            )
        ).scalars().all()
        if not ids:
            return
        last_id = ids[-1]
        await db.execute(
            update(PhotoFace)
            .where(PhotoFace.id.in_(ids))
            .values(person_id=target_id)
            .execution_options(synchronize_session=False)
        )


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

    # Sommes portées par groupe (et non la liste des vecteurs) : mémoire
    # bornée par k × dimension, indépendante du nombre de visages.
    totals: dict[int, list[float]] = {}
    counts: dict[int, int] = {}

    def add_vector(person_id: int, vector: list[float]) -> None:
        total = totals.get(person_id)
        if total is None:
            totals[person_id] = list(vector)
            counts[person_id] = 1
            return
        for index, value in enumerate(vector):
            total[index] += value
        counts[person_id] += 1

    seen = 0
    # 1) Ancres : visages déjà affectés, en paquets (centroides des groupes).
    async for rows in _face_chunks(db, owner_id, assigned=True):
        seen += len(rows)
        for face_id, person_id, embedding in rows:
            if person_id not in person_by_id:
                continue
            add_vector(person_id, list(embedding))

    # Seuls les groupes anonymes sont des cibles automatiques.
    index = FlatFaceIndex(
        {
            person_id: _centroid(totals[person_id], counts[person_id])
            for person_id in totals
            if person_id in anonymous_ids
        }
    )

    assigned = 0
    created = 0
    # 2) Visages non affectés : affectation, en paquets.
    async for rows in _face_chunks(db, owner_id, assigned=False):
        seen += len(rows)
        updates: dict[int, list[int]] = {}
        for face_id, _person_id, embedding in rows:
            vector = list(embedding)
            match = index.search(
                vector, threshold=settings.PHOTO_FACE_GROUP_THRESHOLD
            )
            if match is not None:
                add_vector(match[0], vector)
                index.upsert(match[0], _centroid(totals[match[0]], counts[match[0]]))
                updates.setdefault(match[0], []).append(face_id)
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
                add_vector(person.id, vector)
                index.upsert(
                    person.id, _centroid(totals[person.id], counts[person.id])
                )
                updates.setdefault(person.id, []).append(face_id)
                created += 1
        # Affectations du paquet : UPDATE groupés par cible, en base.
        for person_id, face_ids in updates.items():
            await db.execute(
                update(PhotoFace)
                .where(PhotoFace.id.in_(face_ids))
                .values(person_id=person_id)
                .execution_options(synchronize_session=False)
            )

    if seen == 0:
        return {"assigned": 0, "created": 0, "merged": 0}

    # Fusion des groupes anonymes (paires, k² sur des dizaines d'entrées).
    merged = 0
    for _round in range(_MAX_MERGE_ROUNDS):
        changed = False
        anon_ids = sorted(
            person_id
            for person_id in totals
            if person_id in anonymous_ids
        )
        # Centroïdes calculés une fois par tour (et non par paire) : la
        # comparaison devient un simple produit scalaire.
        centroids = {
            person_id: _centroid(totals[person_id], counts[person_id])
            for person_id in anon_ids
        }
        for position, id_a in enumerate(anon_ids):
            for id_b in anon_ids[position + 1:]:
                similarity = _dot(centroids[id_a], centroids[id_b])
                if similarity < settings.PHOTO_FACE_GROUP_MERGE_THRESHOLD:
                    continue
                # id_b → id_a (ordre déterministe : le plus ancien survive).
                # Les visages sont réaffectés AVANT la suppression de la
                # source (ON DELETE SET NULL ne touche donc plus que des
                # visages déjà migrés).
                await _move_faces(db, id_b, id_a)
                total_a = totals.pop(id_a)
                total_b = totals.pop(id_b)
                totals[id_a] = [
                    value_a + value_b
                    for value_a, value_b in zip_longest(
                        total_a, total_b, fillvalue=0.0
                    )
                ]
                counts[id_a] = counts.pop(id_a) + counts.pop(id_b)
                anonymous_ids.discard(id_b)
                index.remove(id_b)
                centroids.pop(id_b, None)
                centroids[id_a] = _centroid(totals[id_a], counts[id_a])
                index.upsert(id_a, centroids[id_a])
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
    for person_id in totals:
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
