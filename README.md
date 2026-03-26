<<<<<<< HEAD
# Telegram Hotel Bot

Telegram-бот для поиска и подбора отелей через `Booking.com API` (RapidAPI).

## Что умеет бот

- `/lowprice` - показывает самые дешевые отели.
- `/guest_rating` - показывает отели с лучшим рейтингом.
- `/bestdeal` - подбирает варианты по цене/качеству с фильтром диапазона цен.
- `/history` - показывает историю последних поисков пользователя.

## Технологии

- Python 3.10+
- `pyTelegramBotAPI` (TeleBot)
- `requests`
- `peewee` + SQLite (`history.db`)
- `python-dotenv`
- `python-telegram-bot-calendar`

## Быстрый старт

1. Создайте и активируйте виртуальное окружение:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

3. Создайте файл `.env` на основе примера:

   ```bash
   copy .env.example .env
   ```

4. Заполните переменные в `.env`:

   ```env
   BOT_TOKEN=your_telegram_bot_token
   RAPID_API_KEY=your_rapidapi_key
   ```

5. Запустите бота:

   ```bash
   python main.py
   ```

## Docker запуск

1. Соберите образ:

   ```bash
   docker build -t hotel-bot .
   ```

2. Запустите контейнер с переменными окружения:

   ```bash
   docker run --name hotel-bot --env-file .env -d hotel-bot
   ```

## Структура проекта

- `main.py` - обработчики команд и основной сценарий диалога с пользователем.
- `api.py` - запросы к Booking API и нормализация данных отелей.
- `models.py` - модели базы данных и история поиска.
- `loader.py` - инициализация бота, загрузка переменных окружения.
- `requirements.txt` - зависимости проекта.

## Переменные окружения

- `BOT_TOKEN` - токен Telegram-бота от `@BotFather`.
- `RAPID_API_KEY` - ключ RapidAPI для `booking-com15`.

## Лицензия

Проект распространяется под лицензией MIT. См. файл `LICENSE`.
=======
# hotel-telegram-bot
Telegram-бот для поиска и подбора отелей через `Booking.com API` (RapidAPI).
>>>>>>> ee0c38d7cb39ea4284b0880c64229497b92a0b3e
