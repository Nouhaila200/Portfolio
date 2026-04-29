"""
Module d'alerte Telegram.
Envoie des notifications pour chaque nouvelle offre d'emploi trouvée.
"""

import asyncio
import logging
from typing import Dict, Any

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


def format_job_message(job: Dict[str, Any]) -> str:
    """
    Formate un message Telegram lisible pour une offre d'emploi.

    Args:
        job: Dictionnaire contenant les infos de l'offre

    Returns:
        Message HTML formaté pour Telegram
    """
    title    = job.get("title",     "N/A")
    company  = job.get("company",   "N/A")
    location = job.get("location",  "N/A")
    contract = job.get("contract",  "CDI")
    source   = job.get("source",    "N/A")
    url      = job.get("url",       "#")
    published = job.get("published", "")

    date_str = f"\n📅 <b>Publiée :</b> {published}" if published else ""

    message = (
        f"🚀 <b>Nouvelle offre CDI Data</b>\n"
        f"{'─' * 30}\n"
        f"💼 <b>Poste :</b> {title}\n"
        f"🏢 <b>Entreprise :</b> {company}\n"
        f"📍 <b>Lieu :</b> {location}\n"
        f"📝 <b>Contrat :</b> {contract}"
        f"{date_str}\n"
        f"🔗 <b>Source :</b> {source}\n"
        f"{'─' * 30}\n"
        f"👉 <a href='{url}'>Voir l'offre</a>"
    )
    return message


def send_job_alert(bot_token: str, chat_id: str, job: Dict[str, Any]) -> bool:
    """
    Envoie une alerte Telegram pour une offre d'emploi.

    Args:
        bot_token: Token du bot Telegram
        chat_id: ID du chat/groupe destinataire
        job: Dictionnaire contenant les infos de l'offre

    Returns:
        True si le message a été envoyé avec succès, False sinon
    """
    async def _send():
        bot = Bot(token=bot_token)
        message = format_job_message(job)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )

    try:
        asyncio.run(_send())
        logger.info(
            "✅ Alerte envoyée : [%s] %s @ %s",
            job.get("source", "?"),
            job.get("title",  "?"),
            job.get("company","?"),
        )
        return True
    except TelegramError as e:
        logger.error("❌ Erreur Telegram lors de l'envoi : %s", e)
        return False
    except Exception as e:
        logger.error("❌ Erreur inattendue lors de l'envoi Telegram : %s", e)
        return False


def send_summary_alert(bot_token: str, chat_id: str, count: int) -> None:
    """
    Envoie un résumé récapitulatif si plusieurs nouvelles offres ont été trouvées.

    Args:
        bot_token: Token du bot Telegram
        chat_id: ID du chat/groupe destinataire
        count: Nombre total de nouvelles offres trouvées
    """
    async def _send():
        bot = Bot(token=bot_token)
        message = (
            f"📊 <b>Récapitulatif de la veille</b>\n"
            f"🔎 <b>{count}</b> nouvelle(s) offre(s) CDI Data trouvée(s) "
            f"dans les dernières 24h."
        )
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
        )

    try:
        asyncio.run(_send())
        logger.info("📊 Résumé envoyé : %d nouvelle(s) offre(s)", count)
    except TelegramError as e:
        logger.error("❌ Erreur Telegram lors de l'envoi du résumé : %s", e)
    except Exception as e:
        logger.error("❌ Erreur inattendue lors de l'envoi du résumé : %s", e)
