import os
from telebot import TeleBot
from dotenv import load_dotenv
from models import create_models

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
RAPID_API_KEY = os.getenv('RAPID_API_KEY')

bot = TeleBot(BOT_TOKEN)

create_models()
