"""Initialise le référentiel comptable fourni pour l'Intendance."""

from alembic import op
import sqlalchemy as sa


revision = "20261019_0003"
down_revision = "20261019_0002"
branch_labels = None
depends_on = None


_CODES = [
    ("606810-1-333-0279", "Achats non stockés de nourriture", "Nourriture"),
    ("625100-1-333-0279", "Voyages et déplacements", "Déplacements"),
    ("625600-1-333-0279", "Missions", "Déplacements"),
    ("626100-1-333-0279", "Frais postaux", "Administratifs"),
    ("624810-1-333-0279", "Frais de carburant", "Déplacements"),
    ("606310-1-333-0279", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("625700-1-333-0279", "Réceptions", "Nourriture"),
    ("625112-1-333-0279", "Voyages et déplacements (SA)", "Déplacements"),
    ("615500-1-333-0279", "Entretien & réparations des véhicules", "Véhicules"),
    ("606400-1-333-0279", "Fournitures administratives", "Administratifs"),
    ("606370-1-333-0279", "Fournitures d'entretien des véhicules", "Véhicules"),
    ("606310-1-216-0279", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("606310-1-322-0279", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("606310-1-407-0279", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("613500-1-333-0279", "Locations mobilières", "Locations"),
    ("657150-1-333-0279-2793-10S1110-FRA KH Lavelanet - Coume 28 NC-DR (Annulé)-Frais de mise en oeuvre\\Etudes et frais de chantier\\Ingénierie et contrôle qualité", "Dépenses d'aménagement et de construction", "Projets DIVERS"),
    ("657150-1-333-0279-2521-15S2040-FRA KH Abbeville - Paris 212 NC-DR-Frais de personnel\\Frais de personnel\\Structures de logement temporaires", "Dépenses d'aménagement et de construction", "Projets DIVERS"),
    ("657150-1-333-0279-2912-60E1060-FRA OTH Riom - Toulon 2 mR-Salle du Royaume\\Équipement et mobilier\\Équipement ménager", "Dépenses d'aménagement et de construction de lieux de culte (PT)", "Projet RIOM"),
    ("657150-1-333-0279-2912-60E2050-FRA OTH Riom - Toulon 2 mR-Salle du Royaume\\Équipement et mobilier\\Mobilier mobile", "Dépenses d'aménagement et de construction de lieux de culte (PT)", "Projet RIOM"),
    ("657150-1-333-0279-2912-60E2013-FRA OTH Riom - Toulon 2 mR-Salle du Royaume\\Équipement et mobilier\\Placards", "Dépenses d'aménagement et de construction de lieux de culte (PT)", "Projet RIOM"),
    ("657120-1-0279", "Dépenses d'aménagement des lieux de culte", "Projet RIOM"),
    ("657150-1-333-0279-2912-60C1090-FRA OTH Riom - Toulon 2 mR-Salle du Royaume\\Aménagements intérieurs et finitions\\Accessoires d'intérieur", "Dépenses d'aménagement et de construction de lieux de culte (PT)", "Projet RIOM"),
    ("657150-1-333-0279-2588-10S1110-GLP KH Grand Bourg - Basses NC-Frais de mise en oeuvre\\Etudes et frais de chantier\\Ingénierie et contrôle qualité", "Dépenses d'aménagement et de construction", "Projets DIVERS"),
    ("606310-1-319-0279", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("606310-1-333-0277", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("474100-1-0279-528-10S1110-REU KH Ravine des Cabris Collardeau 19Bis MR (Réaménagement) PT annulé-Project Support\\Etudes et frais de chantier\\Ingénierie et contrôle qualité", "Compte transitoire - Projets", "Projets DIVERS"),
    ("657150-1-333-0279-2600-10S1110-FRA KH St Pierre en Faucigny - Bajolet 200 MR-Frais de mise en oeuvre\\Etudes et frais de chantier\\Ingénierie et contrôle qualité", "Dépenses d'aménagement et de construction", "Projets DIVERS"),
    ("017800-1-0371-2894-10S1120-MUS KH Grand Baie - Pointe aux Canonniers NC-PP-Frais de mise en oeuvre\\Etudes et frais de chantier\\Permis de construire", "Work in progress-Kingdom Halls and Assembly Halls", "Projets DIVERS"),
    ("626200-1-333-0284", "Frais de télécommunications", "Energies"),
    ("625610-1-333-0279", "Frais de mission des ministres du culte (déplacements)", "Déplacements"),
    ("606301-1-319-0279", "Logiciels non immobilisés", "Projets DIVERS"),
    ("478000-1-0279", "Compte d'attente divers", "Projets DIVERS"),
    ("606101-1-333-0284", "Eau et énergie", "Energies"),
    ("017800-1-0371-2480-01P2020-MUS KH Surinam PP-NC-Propriété\\Immobilier\\Honoraires", "Work in progress-Kingdom Halls and Assembly Halls", "Projets DIVERS"),
    ("626100-1-311-0279", "Frais postaux", "Administratifs"),
    ("657150-1-333-0279-2912-10S1350-FRA OTH Riom - Toulon 2 mR-Frais de mise en oeuvre\\Etudes et frais de chantier\\Installations temporaires des services", "Dépenses d'aménagement et de construction de lieux", "Projet RIOM"),
    ("409200-1-0279", "Avances et acomptes", "Projets DIVERS"),
    ("617000-1-333-0279", "Etudes et recherches", "Projets DIVERS"),
    ("611200-1-322-0284", "Prestations informatiques et techniques sous-traitées", "Projets DIVERS"),
    ("615500-1-333-0284", "Entretien & réparations des véhicules", "Véhicules"),
    ("657150-1-0284-3115-10S1110-FRA KH Persan - République 3 MR-Frais de mise en oeuvre\\Etudes et frais de chantier\\Ingénierie et contrôle qualité", "Dépenses d'aménagement et de construction", "Projets DIVERS"),
    ("017800-1-0371-2869-01P2020-MUS KH Pamplemousses - Moulin PP-NC-Propriété\\Immobilier\\Honoraires", "Work in progress-Kingdom Halls and Assembly Halls", "Projets DIVERS"),
    ("474100-1-0284-2719-01P1010-FRA KH Ganges PP-NC-Propriété\\Immobilier\\Diagnostics et investigation", "Compte transitoire - Projets Salles du Royaume et Salles d'assemblées", "Projets DIVERS"),
    ("606310-1-333-0284", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("606100-1-216-0279", "Eau et énergie", "Energies"),
    ("626200-1-216-0284", "Frais de télécommunications", "Energies"),
    ("613200-1-216-0279", "Locations immobilières", "Locations"),
    ("635120-1-331-0284", "Taxes foncières", "Taxes foncières"),
    ("606100-1-333-0279", "Eau et énergie", "Energies"),
    ("802810-1-0284", "Engagements donnés - Dispositif de mutualisation (630228 (214)) CEBAZAT", "Energies"),
    ("606130-1-020-0284", "Energie et autres fluides sur legs et donations en cours", "Energies"),
    ("615200-1-333-0279", "Entretien, réparation et contrôle des bâtiments", "Energies"),
    ("275000-1-0279", "Dépôts et cautionnements", "Locations"),
    ("606810-1-333-0284", "Achats non stockés de nourriture", "Nourriture"),
    ("626100-1-333-0284", "Frais postaux", "Administratifs"),
    ("606310-1-216-0284", "Fournitures d'entretien et de petit équipement", "Maintenance"),
    ("657150-1-0284-3025-10S1110-FRA KH Béziers - Corneilhan 208 MR-Frais de mise en oeuvre\\Etudes et frais de chantier\\Ingénierie et contrôle qualité", "Dépenses d'aménagement et de construction", "Projets DIVERS"),
    ("606370-1-333-0284", "Fournitures d'entretien des véhicules", "Véhicules"),
    ("625100-1-333-0284", "Voyages et déplacements", "Déplacements"),
    ("606400-1-333-0284", "Fournitures administratives", "Administratifs"),
    ("624810-1-333-0284", "Frais de carburant et péages", "Déplacements"),
    ("613500-1-333-0284", "Locations mobilières", "Locations"),
    ("606301-1-333-0279", "Logiciels non immobilisés", "Administratifs"),
    ("615500-1-333-0284", "Entretien & réparations des véhicules (mutualisation)", "Véhicules"),
    ("626200-1-216-0279", "Frais de télécommunications", "Energies"),
    ("625600-1-333-0284", "Missions", "Déplacements"),
    ("625100-1-333-0284", "Voyages et déplacements (mutualisation)", "Déplacements"),
]


def upgrade() -> None:
    bind = op.get_bind()
    op.alter_column("intendance_account_codes", "code", existing_type=sa.String(80), type_=sa.String(700), existing_nullable=False)
    op.alter_column("intendance_expenses", "account_code", existing_type=sa.String(80), type_=sa.String(700), existing_nullable=True)
    op.alter_column("intendance_import_staged_rows", "account_code", existing_type=sa.String(80), type_=sa.String(700), existing_nullable=True)
    for code, label, category in _CODES:
        bind.execute(
            sa.text("INSERT IGNORE INTO intendance_account_codes (code, label, category) VALUES (:code, :label, :category)"),
            {"code": code, "label": label, "category": category},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for code, _, _ in _CODES:
        bind.execute(sa.text("DELETE FROM intendance_account_codes WHERE code = :code"), {"code": code})
