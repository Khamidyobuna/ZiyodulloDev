from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from ai_service import generate_ai_reply
from config import AI_TELEGRAM_BOT_TOKEN
from models import init_db


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "Salom. Men ZiyoDev AI botman. O'zbek, English va Русский tillarida savol yuborishingiz mumkin."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.message.text:
        return

    user_identifier = f"telegram:{update.effective_user.id}"
    user_text = update.message.text.strip()

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    reply_text = await asyncio.to_thread(generate_ai_reply, user_identifier, user_text)
    await update.message.reply_text(reply_text)


def main() -> None:
    init_db()
    application = Application.builder().token(AI_TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.run_polling()


if __name__ == "__main__":
    main()
