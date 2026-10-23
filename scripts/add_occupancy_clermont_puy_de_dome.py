#!/usr/bin/env python3
"""
Script pour ajouter des occupations ROSELLO Matthieu et ROSELLO Anaïs
dans le logement CLERMONT - PUY DE DOME du 27/07/2023 au 31/12/2026 statut confirmed.
À exécuter sur le serveur de production.
"""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.housing import Housing, Occupant, Occupancy
from app.models.buildings import Room


async def add_occupancy():
    async with AsyncSessionLocal() as db:
        # 1. Trouver la room "CLERMONT - PUY DE DOME"
        result = await db.execute(
            select(Room).where(Room.name == "CLERMONT - PUY DE DOME")
        )
        room = result.scalar_one_or_none()
        
        if not room:
            print("ERREUR: Room 'CLERMONT - PUY DE DOME' non trouvée")
            return
        
        print(f"Room trouvée: {room.name} (id={room.id}, building_id={room.building_id})")
        
        # 2. Trouver le housing associé
        result = await db.execute(
            select(Housing).where(Housing.room_id == room.id)
        )
        housing = result.scalar_one_or_none()
        
        if not housing:
            print("ERREUR: Housing non trouvé pour cette room")
            return
        
        print(f"Housing trouvé: id={housing.id}")
        
        # 3. Trouver ou créer l'occupant ROSELLO Matthieu
        result = await db.execute(
            select(Occupant).where(
                Occupant.last_name == "ROSELLO",
                Occupant.first_name == "Matthieu"
            )
        )
        occupant_m = result.scalar_one_or_none()
        
        if not occupant_m:
            occupant_m = Occupant(
                first_name="Matthieu",
                last_name="ROSELLO",
                is_active=True
            )
            db.add(occupant_m)
            await db.flush()
            print(f"Occupant créé: {occupant_m.first_name} {occupant_m.last_name} (id={occupant_m.id})")
        else:
            print(f"Occupant existant: {occupant_m.first_name} {occupant_m.last_name} (id={occupant_m.id})")
        
        # 4. Trouver ou créer l'occupant ROSELLO Anaïs
        result = await db.execute(
            select(Occupant).where(
                Occupant.last_name == "ROSELLO",
                Occupant.first_name == "Anaïs"
            )
        )
        occupant_a = result.scalar_one_or_none()
        
        if not occupant_a:
            occupant_a = Occupant(
                first_name="Anaïs",
                last_name="ROSELLO",
                is_active=True
            )
            db.add(occupant_a)
            await db.flush()
            print(f"Occupant créé: {occupant_a.first_name} {occupant_a.last_name} (id={occupant_a.id})")
        else:
            print(f"Occupant existant: {occupant_a.first_name} {occupant_a.last_name} (id={occupant_a.id})")
        
        # 5. Vérifier s'il y a déjà une occupation pour cette période
        result = await db.execute(
            select(Occupancy).where(
                Occupancy.housing_id == housing.id,
                Occupancy.arrival_date <= datetime(2026, 12, 31, tzinfo=timezone.utc),
                Occupancy.departure_date >= datetime(2023, 7, 27, tzinfo=timezone.utc),
                Occupancy.status == "confirmed"
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"ATTENTION: Occupation confirmée déjà existante (id={existing.id})")
            # Vérifier si les occupants sont déjà liés
            for occupant in [occupant_m, occupant_a]:
                if occupant in existing.occupants:
                    print(f"{occupant.first_name} {occupant.last_name} déjà lié à cette occupation")
                else:
                    existing.occupants.append(occupant)
                    print(f"{occupant.first_name} {occupant.last_name} ajouté à l'occupation existante")
        else:
            # 6. Créer la nouvelle occupation avec les deux occupants
            occupancy = Occupancy(
                housing_id=housing.id,
                status="confirmed",
                arrival_date=datetime(2023, 7, 27, tzinfo=timezone.utc),
                departure_date=datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                nb_persons=2,
                occupants=[occupant_m, occupant_a]
            )
            db.add(occupancy)
            print(f"Occupation créée: id={occupancy.id} du 27/07/2023 au 31/12/2026")
        
        await db.commit()
        print("Terminé avec succès")


if __name__ == "__main__":
    asyncio.run(add_occupancy())