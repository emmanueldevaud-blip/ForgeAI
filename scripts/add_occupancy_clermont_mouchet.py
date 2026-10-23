#!/usr/bin/env python3
"""
Script pour ajouter une occupation Sophie LELIEVRE
dans le logement CLERMONT - MOUCHET du 29/09/2021 au 31/12/2026 statut confirmed.
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
        # 1. Trouver la room "CLERMONT - MOUCHET"
        result = await db.execute(
            select(Room).where(Room.name == "CLERMONT - MOUCHET")
        )
        room = result.scalar_one_or_none()
        
        if not room:
            print("ERREUR: Room 'CLERMONT - MOUCHET' non trouvée")
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
        
        # 3. Trouver ou créer l'occupant Sophie LELIEVRE
        result = await db.execute(
            select(Occupant).where(
                Occupant.last_name == "LELIEVRE",
                Occupant.first_name == "Sophie"
            )
        )
        occupant = result.scalar_one_or_none()
        
        if not occupant:
            occupant = Occupant(
                first_name="Sophie",
                last_name="LELIEVRE",
                is_active=True
            )
            db.add(occupant)
            await db.flush()
            print(f"Occupant créé: {occupant.first_name} {occupant.last_name} (id={occupant.id})")
        else:
            print(f"Occupant existant: {occupant.first_name} {occupant.last_name} (id={occupant.id})")
        
        # 4. Vérifier s'il y a déjà une occupation pour cette période
        result = await db.execute(
            select(Occupancy).where(
                Occupancy.housing_id == housing.id,
                Occupancy.arrival_date <= datetime(2026, 12, 31, tzinfo=timezone.utc),
                Occupancy.departure_date >= datetime(2021, 9, 29, tzinfo=timezone.utc),
                Occupancy.status == "confirmed"
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"ATTENTION: Occupation confirmée déjà existante (id={existing.id})")
            # Vérifier si Sophie est déjà liée
            if occupant in existing.occupants:
                print("Sophie LELIEVRE est déjà liée à cette occupation")
                return
            else:
                existing.occupants.append(occupant)
                print("Sophie LELIEVRE ajoutée à l'occupation existante")
        else:
            # 5. Créer la nouvelle occupation
            occupancy = Occupancy(
                housing_id=housing.id,
                status="confirmed",
                arrival_date=datetime(2021, 9, 29, tzinfo=timezone.utc),
                departure_date=datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
                nb_persons=1,
                occupants=[occupant]
            )
            db.add(occupancy)
            print(f"Occupation créée: id={occupancy.id} du 29/09/2021 au 31/12/2026")
        
        await db.commit()
        print("Terminé avec succès")


if __name__ == "__main__":
    asyncio.run(add_occupancy())