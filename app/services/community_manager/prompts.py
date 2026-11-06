"""Prompts pour le Community Manager IA."""

import json
from datetime import datetime, timedelta
from typing import Any


SYSTEM_PROMPT = """
# RÔLE : COMMUNITY MANAGER IA — STRATÉGIE ÉDITORIALE SPORT

Tu es un Community Manager expert spécialisé dans le sport d'endurance (trail, running, triathlon, cyclisme).
Ta mission est de générer un calendrier éditorial cohérent, engageant et aligné sur la stratégie de marque de l'athlète.

## PRINCIPES FONDAMENTAUX

1. **AUTHENTICITÉ** : Chaque sujet doit refléter la vraie vie de l'athlète, ses entraînements réels, ses progrès, ses défis.
2. **PERTINENCE** : Les sujets sont basés sur les activités récentes Garmin (données réelles uniquement).
3. **VARIÉTÉ** : Alterner les formats (éducatif, inspirant, coulisses, performance, lifestyle).
4. **ENGAGEMENT** : Chaque publication doit inciter à l'interaction (question, appel à l'action, partage d'expérience).
5. **COHÉRENCE** : Respecter le ton, les thèmes, la fréquence et les règles définis dans la stratégie.

## FORMAT DE SORTIE OBLIGATOIRE (JSON)

{
  "calendar": [
    {
      "date": "YYYY-MM-DD",
      "topic": "Titre accrocheur du sujet",
      "theme": "running|recovery|nutrition|training|gear|mental|races|lifestyle",
      "objective": "engagement|visibility|brand_awareness|community_building|lead_generation",
      "notes": "Contexte IA : basé sur l'activité du DATE (distance, D+, type, ressenti)",
      "hashtags": "#trail #running #recovery #forgeai"
    },
    ...
  ]
}

## RÈGLES DE GÉNÉRATION

- **date** : Date suggérée (à partir de demain, espacée selon la fréquence)
- **topic** : Titre court, accrocheur, max 100 caractères
- **theme** : Un seul thème parmi la liste autorisée
- **objective** : Un seul objectif parmi la liste autorisée
- **notes** : Explication du lien avec les données réelles (activité, métriques, ressenti)
- **hashtags** : 5-10 hashtags pertinents, mélange niche et large

## CONTRAINTES

- Ne JAMAIS inventer de résultats, performances ou données
- Utiliser UNIQUEMENT les activités Garmin réelles comme source
- Respecter les topics interdits et les règles de la stratégie
- Adapter le ton selon la stratégie (professional, inspirational, casual, expert, motivational, educational)
"""


def build_generation_prompt(
    strategy: dict[str, Any],
    recent_activities: list[dict[str, Any]],
    count: int,
    start_date: datetime | None = None,
) -> str:
    """Construit le prompt pour la génération du calendrier éditorial."""

    if start_date is None:
        start_date = datetime.now() + timedelta(days=1)

    # Formater les activités récentes pour le prompt
    activities_text = ""
    if recent_activities:
        activities_text = "ACTIVITÉS RÉCENTES GARMIN (données réelles) :\n"
        for act in recent_activities[:10]:
            started = act.get("started_at", "")
            sport = act.get("sport_type", "")
            dist = act.get("distance_m")
            elev = act.get("elevation_gain_m")
            dur = act.get("duration_seconds")
            name = act.get("activity_name", "")
            hr = act.get("avg_heart_rate")
            pace = act.get("avg_pace_sec_km")

            dist_str = f"{dist/1000:.1f} km" if dist else "N/A"
            elev_str = f"{int(elev)} m D+" if elev else "N/A"
            dur_str = f"{dur//3600}h{(dur%3600)//60:02d}" if dur else "N/A"
            hr_str = f"{int(hr)} bpm" if hr else "N/A"
            pace_str = f"{int(pace//60)}:{int(pace%60):02d}/km" if pace else "N/A"

            activities_text += (
                f"- {started[:10]} | {sport} | {name} | {dist_str} | {elev_str} | {dur_str} | FC: {hr_str} | Allure: {pace_str}\n"
            )
    else:
        activities_text = "AUCUNE ACTIVITÉ RÉCENTE DISPONIBLE — Générer des sujets evergreen basés sur les thèmes de la stratégie.\n"

    # Calculer les dates suggérées
    freq = strategy.get("frequency", 3)
    days_between = max(1, 7 // freq) if freq > 0 else 2
    dates = [(start_date + timedelta(days=i * days_between)).strftime("%Y-%m-%d") for i in range(count)]

    prompt = f"""
{activities_text}

STRATÉGIE ÉDITORIALE :
- Identité de marque : {strategy.get("brand_identity", "Non définie")}
- Ton : {", ".join(strategy.get("tone", []))}
- Audience cible : {strategy.get("target_audience", "Non définie")}
- Objectifs : {", ".join(strategy.get("objectives", []))}
- Thèmes autorisés : {", ".join(strategy.get("themes", []))}
- Fréquence : {freq} publications/semaine
- Réseaux : {", ".join(strategy.get("networks", []))}
- Règles : {"; ".join(strategy.get("rules", []))}
- Topics interdits : {", ".join(strategy.get("forbidden_topics", []))}

GÉNÉRER {count} SUJETS DE PUBLICATION pour les dates suivantes : {", ".join(dates)}

IMPORTANT :
- Chaque sujet doit être lié à une activité réelle si possible (citer la date et le type d'activité dans les notes)
- Si pas d'activité récente, créer des sujets evergreen (conseils, éducation, lifestyle) dans les thèmes autorisés
- Respecter scrupuleusement les règles et topics interdits
- Varier les thèmes et objectifs sur l'ensemble du calendrier
- Format de sortie : JSON strict avec la clé "calendar"
"""
    return prompt


def build_strategy_prompt() -> str:
    """Prompt pour aider l'utilisateur à définir sa stratégie (non utilisé en V1, pour référence)."""
    return """
Définissez votre stratégie éditoriale pour le Community Manager IA.
Cette stratégie guidera la génération automatique de votre calendrier de publications.
"""