"""
Module de stockage : gestion du fichier JSON des offres déjà vues.
Permet d'éviter les doublons entre les différentes passes de scraping.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)


def _load(filepath: str) -> dict:
    """
    Charge le fichier JSON de stockage.

    Args:
        filepath: Chemin vers le fichier JSON

    Returns:
        Dictionnaire avec clés 'seen_ids' et 'last_updated'
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        return {"seen_ids": [], "last_updated": None}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Compatibilité si le fichier est vide ou malformé
            if not isinstance(data, dict):
                return {"seen_ids": [], "last_updated": None}
            return data
    except (json.JSONDecodeError, OSError) as e:
        logger.error("❌ Erreur lecture seen_jobs.json : %s — fichier réinitialisé.", e)
        return {"seen_ids": [], "last_updated": None}


def _save(filepath: str, data: dict) -> None:
    """
    Sauvegarde le dictionnaire dans le fichier JSON.

    Args:
        filepath: Chemin vers le fichier JSON
        data: Données à sauvegarder
    """
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("❌ Erreur écriture seen_jobs.json : %s", e)


def get_seen_ids(filepath: str) -> Set[str]:
    """
    Retourne l'ensemble des IDs d'offres déjà traitées.

    Args:
        filepath: Chemin vers le fichier JSON de stockage

    Returns:
        Ensemble d'identifiants d'offres vus
    """
    data = _load(filepath)
    return set(data.get("seen_ids", []))


def mark_as_seen(filepath: str, job_id: str) -> None:
    """
    Marque une offre comme vue et persiste le changement.

    Args:
        filepath: Chemin vers le fichier JSON de stockage
        job_id: Identifiant unique de l'offre
    """
    data = _load(filepath)
    seen = set(data.get("seen_ids", []))

    if job_id not in seen:
        seen.add(job_id)
        data["seen_ids"] = sorted(seen)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        _save(filepath, data)
        logger.debug("📌 Offre marquée comme vue : %s", job_id)


def mark_batch_as_seen(filepath: str, job_ids: list) -> None:
    """
    Marque un lot d'offres comme vues en une seule écriture (plus efficace).

    Args:
        filepath: Chemin vers le fichier JSON de stockage
        job_ids: Liste d'identifiants à marquer
    """
    if not job_ids:
        return

    data = _load(filepath)
    seen = set(data.get("seen_ids", []))
    seen.update(job_ids)
    data["seen_ids"] = sorted(seen)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save(filepath, data)
    logger.debug("📌 %d offre(s) marquée(s) comme vues.", len(job_ids))


def is_new(filepath: str, job_id: str) -> bool:
    """
    Vérifie si une offre est nouvelle (non encore vue).

    Args:
        filepath: Chemin vers le fichier JSON de stockage
        job_id: Identifiant unique de l'offre

    Returns:
        True si l'offre n'a pas encore été traitée
    """
    return job_id not in get_seen_ids(filepath)
