"""
Source : Welcome to the Jungle — Scraping RSS + HTML
Le site expose un flux RSS public par catégorie.
URL RSS : https://www.welcometothejungle.com/fr/jobs/rss?...
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from urllib.parse import urlencode

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)

# --- Constantes ---
RSS_BASE = "https://www.welcometothejungle.com/fr/jobs/rss"
SEARCH_BASE = "https://www.welcometothejungle.com/fr/jobs"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def _build_rss_url(keyword: str) -> str:
    """
    Construit l'URL du flux RSS WTTJ pour un mot-clé.

    Args:
        keyword: Intitulé de poste

    Returns:
        URL du flux RSS
    """
    params = {
        "query": keyword,
        "contract_type[]": "CDI",
        "aroundQuery": "France",
    }
    return f"{RSS_BASE}?{urlencode(params)}"


def _fetch_rss(keyword: str, max_age_hours: int) -> List[Dict[str, Any]]:
    """
    Parse le flux RSS WTTJ pour un mot-clé et filtre par ancienneté.

    Args:
        keyword: Intitulé de poste
        max_age_hours: Ancienneté maximale en heures

    Returns:
        Liste d'offres normalisées
    """
    url = _build_rss_url(keyword)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except requests.RequestException as e:
        logger.error("❌ WTTJ RSS erreur réseau pour '%s' : %s", keyword, e)
        return []
    except Exception as e:
        logger.error("❌ WTTJ RSS erreur inattendue pour '%s' : %s", keyword, e)
        return []

    jobs = []
    for entry in feed.entries:
        try:
            # Filtrage par date
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                pub_dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            # Filtrage CDI (le titre ou les tags doivent mentionner CDI)
            tags = [t.get("term", "").lower() for t in entry.get("tags", [])]
            title_lower = entry.get("title", "").lower()
            summary_lower = entry.get("summary", "").lower()
            is_cdi = (
                "cdi" in tags
                or "cdi" in summary_lower
                or "cdi" in title_lower
                or not tags  # Si pas de tag, on inclut (sera filtré après)
            )
            if not is_cdi:
                continue

            # Extraction localisation depuis le résumé HTML
            location = _extract_location(entry.get("summary", ""))

            # ID stable basé sur l'URL
            job_url = entry.get("link", "")
            job_id = "wttj_" + hashlib.md5(job_url.encode()).hexdigest()[:12]

            published_raw = entry.get("published", "")
            try:
                published = dateparser.parse(published_raw).strftime("%d/%m/%Y %H:%M") if published_raw else ""
            except Exception:
                published = published_raw

            jobs.append({
                "id": job_id,
                "title": entry.get("title", "N/A"),
                "company": _extract_company(entry),
                "location": location or "France",
                "contract": "CDI",
                "url": job_url,
                "published": published,
                "source": "Welcome to the Jungle",
            })
        except Exception as e:
            logger.debug("Erreur parsing entrée WTTJ : %s", e)
            continue

    logger.info("WTTJ RSS — '%s' : %d offre(s) éligible(s)", keyword, len(jobs))
    return jobs


def _extract_location(html_summary: str) -> str:
    """
    Extrait la localisation depuis le résumé HTML d'une entrée RSS WTTJ.

    Args:
        html_summary: Résumé HTML de l'entrée RSS

    Returns:
        Localisation sous forme de chaîne
    """
    try:
        soup = BeautifulSoup(html_summary, "lxml")
        text = soup.get_text(separator=" ")
        # Recherche de patterns courants : "Paris", "Lyon", "Remote"
        for token in text.split():
            if token in ("Paris", "Lyon", "Marseille", "Bordeaux", "Toulouse",
                         "Nantes", "Lille", "Strasbourg", "Remote", "Télétravail",
                         "France", "Rennes", "Montpellier", "Nice", "Grenoble"):
                return token
    except Exception:
        pass
    return ""


def _extract_company(entry: dict) -> str:
    """
    Tente d'extraire le nom de l'entreprise depuis les champs de l'entrée RSS.

    Args:
        entry: Entrée feedparser

    Returns:
        Nom de l'entreprise
    """
    # WTTJ met souvent le nom en format "Poste — Entreprise"
    title = entry.get("title", "")
    if " — " in title:
        return title.split(" — ")[-1].strip()
    if " - " in title:
        return title.split(" - ")[-1].strip()
    return entry.get("author", "N/A")


def fetch_jobs(
    keywords: List[str],
    max_age_hours: int = 24,
    location: str = "",
) -> List[Dict[str, Any]]:
    """
    Point d'entrée principal pour Welcome to the Jungle.
    Agrège les offres pour tous les mots-clés et déduplique.

    Args:
        keywords: Liste de titres de postes à rechercher
        max_age_hours: Ancienneté maximale des offres
        location: Ville (non utilisé ici, filtrage géo via RSS)

    Returns:
        Liste dédupliquée d'offres normalisées
    """
    all_jobs: List[Dict[str, Any]] = []
    seen_ids = set()

    for kw in keywords:
        jobs = _fetch_rss(kw, max_age_hours)
        for job in jobs:
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                all_jobs.append(job)

    logger.info("WTTJ — total unique : %d offre(s)", len(all_jobs))
    return all_jobs
