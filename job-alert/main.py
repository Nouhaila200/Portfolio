"""
job-alert — Point d'entrée principal
=====================================
Orchestre la veille d'offres CDI Data depuis plusieurs sources,
filtre les doublons, envoie des alertes Telegram et planifie les passages.

Usage :
    python main.py               # Boucle infinie planifiée
    python main.py --once        # Exécution unique immédiate (test)
    python main.py --dry-run     # Exécution sans envoi Telegram
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

import schedule
import time
import yaml

# --- Import des modules internes ---
from sources.france_travail import fetch_jobs as fetch_france_travail
from sources.welcome_to_the_jungle import fetch_jobs as fetch_wttj
from sources.indeed import fetch_jobs as fetch_indeed
from alerting.telegram import send_job_alert, send_summary_alert
from storage.storage import get_seen_ids, mark_batch_as_seen

# ---------------------------------------------------------------------------
# Configuration du logging
# ---------------------------------------------------------------------------

def setup_logging(log_level: str = "INFO") -> None:
    """Configure le système de logging avec formatage coloré."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("job_alert.log", encoding="utf-8"),
        ],
    )

logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Chargement de la configuration
# ---------------------------------------------------------------------------

def load_config(config_path: str = "config.yaml") -> dict:
    """
    Charge le fichier de configuration YAML.

    Args:
        config_path: Chemin vers le fichier config.yaml

    Returns:
        Dictionnaire de configuration

    Raises:
        SystemExit: Si le fichier est introuvable ou invalide
    """
    path = Path(config_path)
    if not path.exists():
        logger.critical("❌ Fichier de configuration introuvable : %s", config_path)
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info("✅ Configuration chargée depuis %s", config_path)
        return config
    except yaml.YAMLError as e:
        logger.critical("❌ Erreur de parsing YAML : %s", e)
        sys.exit(1)

# ---------------------------------------------------------------------------
# Collecte des offres depuis toutes les sources
# ---------------------------------------------------------------------------

def collect_all_jobs(config: dict) -> List[Dict[str, Any]]:
    """
    Lance la collecte depuis toutes les sources configurées.

    Args:
        config: Dictionnaire de configuration

    Returns:
        Liste agrégée de toutes les offres trouvées
    """
    keywords: List[str] = config.get("keywords", [])
    max_age: int = config["settings"].get("max_age_hours", 24)
    city: str = config["location"].get("city", "")
    ft_cfg = config.get("france_travail", {})

    all_jobs: List[Dict[str, Any]] = []

    # --- France Travail ---
    logger.info("🔍 Collecte France Travail…")
    try:
        ft_jobs = fetch_france_travail(
            client_id=ft_cfg.get("client_id", ""),
            client_secret=ft_cfg.get("client_secret", ""),
            keywords=keywords,
            max_age_hours=max_age,
            location=city,
        )
        all_jobs.extend(ft_jobs)
    except Exception as e:
        logger.error("❌ France Travail a échoué : %s", e)

    # --- Welcome to the Jungle ---
    logger.info("🔍 Collecte Welcome to the Jungle…")
    try:
        wttj_jobs = fetch_wttj(
            keywords=keywords,
            max_age_hours=max_age,
            location=city,
        )
        all_jobs.extend(wttj_jobs)
    except Exception as e:
        logger.error("❌ Welcome to the Jungle a échoué : %s", e)

    # --- Indeed ---
    logger.info("🔍 Collecte Indeed…")
    try:
        indeed_jobs = fetch_indeed(
            keywords=keywords,
            max_age_hours=max_age,
            location=city or "France",
        )
        all_jobs.extend(indeed_jobs)
    except Exception as e:
        logger.error("❌ Indeed a échoué : %s", e)

    logger.info("📦 Total offres collectées (toutes sources) : %d", len(all_jobs))
    return all_jobs

# ---------------------------------------------------------------------------
# Filtrage des nouvelles offres (anti-doublons)
# ---------------------------------------------------------------------------

def filter_new_jobs(
    all_jobs: List[Dict[str, Any]],
    seen_file: str,
) -> List[Dict[str, Any]]:
    """
    Élimine les offres déjà traitées lors de passes précédentes.

    Args:
        all_jobs: Liste complète des offres collectées
        seen_file: Chemin vers le fichier JSON de stockage

    Returns:
        Sous-liste des nouvelles offres uniquement
    """
    seen_ids = get_seen_ids(seen_file)
    new_jobs = [j for j in all_jobs if j["id"] not in seen_ids]

    # Déduplication intra-passe (même ID depuis plusieurs sources)
    unique: Dict[str, Dict] = {}
    for job in new_jobs:
        if job["id"] not in unique:
            unique[job["id"]] = job

    result = list(unique.values())
    logger.info(
        "🆕 Nouvelles offres après filtre : %d / %d",
        len(result), len(all_jobs),
    )
    return result

# ---------------------------------------------------------------------------
# Passe principale
# ---------------------------------------------------------------------------

def run_pass(config: dict, dry_run: bool = False) -> None:
    """
    Exécute une passe complète : collecte → filtre → alerte → stockage.

    Args:
        config: Dictionnaire de configuration
        dry_run: Si True, n'envoie pas d'alertes Telegram
    """
    logger.info("=" * 60)
    logger.info("🚀 Début de la passe de veille")
    logger.info("=" * 60)

    tg_cfg = config["telegram"]
    bot_token: str = tg_cfg.get("bot_token", "")
    chat_id: str = str(tg_cfg.get("chat_id", ""))
    seen_file: str = config["settings"].get("seen_jobs_file", "storage/seen_jobs.json")

    # 1. Collecte
    all_jobs = collect_all_jobs(config)
    if not all_jobs:
        logger.info("ℹ️  Aucune offre collectée cette passe.")
        return

    # 2. Filtrage doublons
    new_jobs = filter_new_jobs(all_jobs, seen_file)
    if not new_jobs:
        logger.info("ℹ️  Aucune nouvelle offre (tout déjà vu).")
        return

    # 3. Alertes Telegram + stockage
    sent_count = 0
    new_ids = []

    for job in new_jobs:
        new_ids.append(job["id"])
        if not dry_run:
            success = send_job_alert(bot_token, chat_id, job)
            if success:
                sent_count += 1
        else:
            logger.info(
                "[DRY-RUN] Offre : %s | %s | %s | %s",
                job["title"], job["company"], job["location"], job["source"],
            )
            sent_count += 1

    # 4. Persistance des IDs vus
    mark_batch_as_seen(seen_file, new_ids)

    # 5. Résumé (si > 1 offre et pas en dry-run)
    if sent_count > 1 and not dry_run:
        send_summary_alert(bot_token, chat_id, sent_count)

    logger.info(
        "✅ Passe terminée — %d nouvelle(s) offre(s) envoyée(s).",
        sent_count,
    )

# ---------------------------------------------------------------------------
# Planification
# ---------------------------------------------------------------------------

def schedule_loop(config: dict, dry_run: bool) -> None:
    """
    Démarre la boucle de planification. Exécute la première passe
    immédiatement, puis toutes les N minutes.

    Args:
        config: Dictionnaire de configuration
        dry_run: Mode sans envoi Telegram
    """
    interval = config["settings"].get("check_interval_minutes", 30)
    logger.info("⏰ Planification toutes les %d minutes.", interval)

    # Première passe immédiate
    run_pass(config, dry_run)

    schedule.every(interval).minutes.do(run_pass, config=config, dry_run=dry_run)

    logger.info("🔄 Boucle de planification démarrée. Ctrl+C pour arrêter.")
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("👋 Arrêt demandé par l'utilisateur.")
            sys.exit(0)
        except Exception as e:
            logger.error("❌ Erreur dans la boucle de planification : %s", e)
            time.sleep(60)  # Pause avant retry

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse les arguments CLI."""
    parser = argparse.ArgumentParser(
        description="Veille automatique d'offres CDI Data en France",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Chemin vers le fichier de configuration (défaut : config.yaml)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exécuter une seule passe puis quitter",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exécuter sans envoyer d'alertes Telegram (test)",
    )
    return parser.parse_args()


def main() -> None:
    """Point d'entrée principal."""
    args = parse_args()
    config = load_config(args.config)

    # Logging
    log_level = config["settings"].get("log_level", "INFO")
    setup_logging(log_level)

    if args.dry_run:
        logger.warning("⚠️  Mode DRY-RUN activé : aucune alerte Telegram ne sera envoyée.")

    if args.once:
        logger.info("📌 Exécution unique (--once)")
        run_pass(config, dry_run=args.dry_run)
    else:
        schedule_loop(config, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
