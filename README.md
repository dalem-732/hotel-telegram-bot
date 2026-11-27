# Telegram Hotel Bot

Telegram-бот для поиска и подбора отелей через Booking.com API (RapidAPI `booking-com15`).

## Что умеет бот

- `/lowprice` - самые дешёвые отели (`sort_by=price`).
- `/guest_rating` - отели с лучшим рейтингом отзывов (`sort_by=bayesian_review_score`).
- `/bestdeal` - лучшие отзывы при низкой цене (`sort_by=review_score_and_price`) с фильтром диапазона цен.
- `/history` - история последних поисков текущего пользователя.
- `/cancel` - отменить текущий поиск.

Команды дублируются кнопками меню. Ссылки на бронирование и карту отправляются кнопками, в историю попадают только адреса `booking.com`.

## Технологии

- Python 3.10+
- `pyTelegramBotAPI` (TeleBot), однопоточный режим
- `requests`
- `peewee` + SQLite
- `python-dotenv`
- `python-telegram-bot-calendar`

## Быстрый старт

1. Создайте и активируйте виртуальное окружение:

   ```bash
   python -m venv .venv
   ```

   Linux и macOS:

   ```bash
   source .venv/bin/activate
   ```

   Windows:

   ```bat
   .venv\Scripts\activate
   ```

2. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```

   Для тестов:

   ```bash
   pip install -r requirements-dev.txt
   pytest
   ```

3. Создайте файл `.env` на основе примера:

   Linux и macOS:

   ```bash
   cp .env.example .env
   ```

   Windows:

   ```bat
   copy .env.example .env
   ```

4. Заполните переменные в `.env`:

   ```env
   BOT_TOKEN=your_telegram_bot_token
   RAPID_API_KEY=your_rapidapi_key
   DATABASE_PATH=history.db
   ```

5. Запустите бота:

   ```bash
   python main.py
   ```

Бот не запустится, если не заданы `BOT_TOKEN` или `RAPID_API_KEY`.

## Docker

1. Соберите образ:

   ```bash
   docker build -t hotel-bot .
   ```

2. Запустите контейнер с файлом окружения и томом для базы, чтобы история не терялась после перезапуска:

   ```bash
   docker run --name hotel-bot --env-file .env -v hotel-bot-data:/data -d hotel-bot
   ```

Образ работает не от root. Путь к базе по умолчанию внутри контейнера - `/data/history.db`. Его можно переопределить переменной `DATABASE_PATH`.

## Структура проекта

- `main.py` - обработчики команд и сценарий диалога.
- `api.py` - запросы к Booking API (`booking-com15`) и нормализация данных отелей.
- `models.py` - модели базы данных и история поиска.
- `loader.py` - конфигурация, проверка переменных окружения и инициализация бота.
- `utils.py` - валидация ввода, лимиты, кэш ссылок и безопасное форматирование сообщений.
- `requirements.txt` - зависимости приложения.
- `requirements-dev.txt` - зависимости для тестов и аудита.

## Переменные окружения

- `BOT_TOKEN` - токен Telegram-бота от `@BotFather`. Обязателен.
- `RAPID_API_KEY` - ключ RapidAPI для `booking-com15`. Обязателен.
- `DATABASE_PATH` - путь к файлу SQLite с историей. По умолчанию `history.db`, в Docker - `/data/history.db`.

## Лицензия

Проект распространяется под лицензией MIT. См. файл `LICENSE`.
