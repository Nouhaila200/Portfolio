"""
Source : France Travail (ex Pôle Emploi) — API Offres d'emploi v2
Documentation : https://francetravail.io/data/api/offres-emploi
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

import requests
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)

# --- Constantes ---
AUTH_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
API_BASE = "https://api.francetravail.io/partenaire/offresdemploi/v2"
SCOPE = "api_offresdemploiv2 o2dsoffre"


def _get_access_token(client_id: str, client_secret: str) -> Optional[str]:
    """
    Obtient un token OAuth2 auprès de France Travail.

    Args:
        client_id: Identifiant client de l'application
        client_secret: Secret client de l'application

    Returns:
        Token d'accès ou None en cas d'erreur
    """
    try:
        response = requests.post(
            AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": SCOPE,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        logger.debug("🔑 Token France Travail obtenu.")
        return token
    except requests.RequestException as e:
        logger.error("❌ Impossible d'obtenir le token France Travail : %s", e)
        return None


def _search_jobs(
    token: str,
    keyword: str,
    max_age_hours: int,
    location: str = "",
) -> List[Dict[str, Any]]:
    """
    Interroge l'API France Travail pour un mot-clé donné.

    Args:
        token: Token OAuth2
        keyword: Intitulé de poste recherché
        max_age_hours: Ancienneté maximale de l'offre en heures
        location: Département ou commune (optionnel)

    Returns:
        Liste de dictionnaires normalisés représentant les offres
    """
    since = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    min_date = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "motsCles": keyword,
        "typeContrat": "CDI",
        "minCreationDate": min_date,
        "range": "0-149",   # max autorisé par l'API
    }
    if location:
        params["commune"] = location

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    try:
        response = requests.get(
            f"{API_BASE}/offres/search",
            params=params,
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        raw_jobs = data.get("resultats", [])
        logger.info(
            "France Travail — '%s' : %d offre(s) trouvée(s)", keyword, len(raw_jobs)
        )
        return [_normalize(job) for job in raw_jobs]
    except requests.HTTPError as e:
        logger.error(
            "❌ France Travail HTTP error pour '%s' : %s — %s",
            keyword, e, e.response.text if e.response else "",
        )
    except requests.RequestException as e:
        logger.error("❌ France Travail erreur réseau pour '%s' : %s", keyword, e)
    except Exception as e:
        logger.error("❌ France Travail erreur inattendue pour '%s' : %s", keyword, e)

    return []


def _normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise une offre brute de l'API France Travail vers le format interne.

    Args:
        raw: Offre brute retournée par l'API

    Returns:
        Dictionnaire normalisé
    """
    lieu = raw.get("lieuTravail", {})
    location = lieu.get("libelle", "France")

    published_raw = raw.get("dateCreation", "")
    try:
        published = dateparser.parse(published_raw).strftime("%d/%m/%Y %H:%M") if published_raw else ""
    except Exception:
        published = published_raw

    return {
        "id": f"ft_{raw.get('id', '')}",
        "title": raw.get("intitule", "N/A"),
        "company": raw.get("entreprise", {}).get("nom", "Entreprise non précisée"),
        "location": location,
        "contract": raw.get("typeContratLibelle", "CDI"),
        "url": raw.get("origineOffre", {}).get(
            "urlOrigine",
            f"https://candidat.francetravail.fr/offres/recherche/detail/{raw.get('id', '')}",
        ),
        "published": published,
        "source": "France Travail",
    }


def fetch_jobs(
    client_id: str,
    client_secret: str,
    keywords: List[str],
    max_age_hours: int = 24,
    location: str = "",
) -> List[Dict[str, Any]]:
    """
    Point d'entrée principal pour France Travail.
    Récupère les offres CDI Data fraîches pour tous les mots-clés.

    Args:
        client_id: Identifiant client API France Travail
        client_secret: Secret client API France Travail
        keywords: Liste de titres de postes à rechercher
        max_age_hours: Ancienneté maximale des offres en heures
        location: Ville ou département (optionnel)

    Returns:
        Liste dédupliquée d'offres normalisées
    """
    token = _get_access_token(client_id, client_secret)
    if not token:
        logger.warning("⚠️ France Travail ignoré (token indisponible).")
        return []

    all_jobs: List[Dict[str, Any]] = []
    seen_ids = set()

    for kw in keywords:
        jobs = _search_jobs(token, kw, max_age_hours, location)
        for job in jobs:
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                all_jobs.append(job)

    logger.info("France Travail — total unique : %d offre(s)", len(all_jobs))
    return all_jobs
