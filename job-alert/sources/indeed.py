"""
Source : Indeed France — Scraping RSS
Indeed expose des flux RSS publics structurés par requête.
URL : https://fr.indeed.com/rss?q=...&l=France&sort=date
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
RSS_BASE = "https://fr.indeed.com/rss"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

CDI_KEYWORDS = {"cdi", "permanent", "full-time", "temps plein", "indéterminée"}


def _build_rss_url(keyword: str, location: str = "France") -> str:
    """
    Construit l'URL RSS Indeed pour un mot-clé et une localisation.

    Args:
        keyword: Intitulé de poste
        location: Localisation géographique

    Returns:
        URL du flux RSS Indeed
    """
    params = {
        "q": f'"{keyword}" CDI',
        "l": location or "France",
        "sort": "date",
        "fromage": "1",  # offres des dernières 24h
        "lang": "fr",
    }
    return f"{RSS_BASE}?{urlencode(params)}"


def _is_cdi(entry: dict) -> bool:
    """
    Heuristique pour détecter si une offre est un CDI.
    Indeed ne filtre pas toujours parfaitement par contrat via RSS.

    Args:
        entry: Entrée feedparser

    Returns:
        True si l'offre semble être un CDI
    """
    text = (
        entry.get("title", "") + " " +
        entry.get("summary", "")
    ).lower()

    # Exclusion explicite d'autres contrats
    if any(kw in text for kw in ("cdd", "intérim", "interim", "stage", "alternance", "freelance")):
        return False
    # Inclusion si mention CDI
    if any(kw in text for kw in CDI_KEYWORDS):
        return True
    # Offre ambiguë : inclure par défaut (mieux vaut trop que pas assez)
    return True


def _extract_location(entry: dict) -> str:
    """
    Extrait la localisation depuis une entrée RSS Indeed.

    Args:
        entry: Entrée feedparser

    Returns:
        Localisation sous forme de chaîne
    """
    # Indeed met parfois la localisation dans le titre : "Data Engineer - Paris"
    title = entry.get("title", "")
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) >= 2:
            candidate = parts[-1].strip()
            if len(candidate) < 40:  # heuristique : une ville est courte
                return candidate

    # Fallback : parsing du champ summary HTML
    try:
        soup = BeautifulSoup(entry.get("summary", ""), "lxml")
        text = soup.get_text()
        for token in text.split("\n"):
            t = token.strip()
            if t and len(t) < 50:
                return t
    except Exception:
        pass

    return "France"


def _extract_company(entry: dict) -> str:
    """
    Extrait le nom de l'entreprise depuis une entrée RSS Indeed.

    Args:
        entry: Entrée feedparser

    Returns:
        Nom de l'entreprise
    """
    # Format titre Indeed : "Poste - Entreprise - Ville"
    title = entry.get("title", "")
    parts = title.split(" - ")
    if len(parts) >= 3:
        return parts[1].strip()
    if len(parts) == 2:
        return parts[1].strip()

    # Essai via author
    return entry.get("author", "N/A")


def _fetch_rss(keyword: str, max_age_hours: int, location: str = "France") -> List[Dict[str, Any]]:
    """
    Parse le flux RSS Indeed et filtre par ancienneté et type de contrat.

    Args:
        keyword: Intitulé de poste
        max_age_hours: Ancienneté maximale en heures
        location: Localisation géographique

    Returns:
        Liste d'offres normalisées
    """
    url = _build_rss_url(keyword, location)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
    except requests.RequestException as e:
        logger.error("❌ Indeed RSS erreur réseau pour '%s' : %s", keyword, e)
        return []
    except Exception as e:
        logger.error("❌ Indeed RSS erreur inattendue pour '%s' : %s", keyword, e)
        return []

    jobs = []
    for entry in feed.entries:
        try:
            # Filtrage temporel
            pub_parsed = entry.get("published_parsed")
            if pub_parsed:
                pub_dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue

            # Filtrage CDI
            if not _is_cdi(entry):
                continue

            job_url = entry.get("link", "")
            job_id = "indeed_" + hashlib.md5(job_url.encode()).hexdigest()[:12]

            published_raw = entry.get("published", "")
            try:
                published = dateparser.parse(published_raw).strftime("%d/%m/%Y %H:%M") if published_raw else ""
            except Exception:
                published = published_raw

            # Nettoyage du titre (enlève " - Ville" en doublon)
            raw_title = entry.get("title", "N/A")
            clean_title = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title

            jobs.append({
                "id": job_id,
                "title": clean_title,
                "company": _extract_company(entry),
                "location": _extract_location(entry),
                "contract": "CDI",
                "url": job_url,
                "published": published,
                "source": "Indeed",
            })
        except Exception as e:
            logger.debug("Erreur parsing entrée Indeed : %s", e)
            continue

    logger.info("Indeed RSS — '%s' : %d offre(s) éligible(s)", keyword, len(jobs))
    return jobs


def fetch_jobs(
    keywords: List[str],
    max_age_hours: int = 24,
    location: str = "France",
) -> List[Dict[str, Any]]:
    """
    Point d'entrée principal pour Indeed.
    Agrège les offres pour tous les mots-clés et déduplique.

    Args:
        keywords: Liste de titres de postes à rechercher
        max_age_hours: Ancienneté maximale des offres
        location: Localisation géographique (France par défaut)

    Returns:
        Liste dédupliquée d'offres normalisées
    """
    all_jobs: List[Dict[str, Any]] = []
    seen_ids = set()

    for kw in keywords:
        jobs = _fetch_rss(kw, max_age_hours, location or "France")
        for job in jobs:
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                all_jobs.append(job)

    logger.info("Indeed — total unique : %d offre(s)", len(all_jobs))
    return all_jobs
