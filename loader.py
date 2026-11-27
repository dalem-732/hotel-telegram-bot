import os
import sys

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
RAPID_API_KEY = os.getenv("RAPID_API_KEY")

_bot = None


def require_config():
    missing = [
        name
        for name, value in (("BOT_TOKEN", BOT_TOKEN), ("RAPID_API_KEY", RAPID_API_KEY))
        if not value
    ]
    if missing:
        sys.stderr.write(
            "Не заданы обязательные переменные окружения: " + ", ".join(missing) + ".\n"
        )
        raise SystemExit(1)


def get_bot():
    global _bot
    if _bot is None:
        require_config()
        from telebot import TeleBot
        _bot = TeleBot(BOT_TOKEN, threaded=False)
    return _bot


def init_app():
    require_config()
    from models import create_models
    create_models()
    return get_bot()
