import time
import datetime
from telebot.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram_bot_calendar import DetailedTelegramCalendar

from loader import get_bot, init_app
from api import search_city, search_hotels, HotelApiError, SORT_BY
from models import upsert_user, SearchHistory
from utils import (
    parse_price_range,
    is_allowed_booking_url,
    is_http_url,
    maps_url,
    validate_stay_dates,
    sanitize_city_query,
    RateLimiter,
    hotel_caption,
    history_item_html,
)

bot = get_bot()

user_states = {}
STATE_TTL_SEC = 15 * 60
city_limiter = RateLimiter(max_calls=5, window_sec=60)
hotel_limiter = RateLimiter(max_calls=3, window_sec=60)

API_ERROR_MESSAGES = {
    "rate_limit": "Сервис поиска временно ограничил запросы. Попробуйте через минуту.",
    "forbidden": "Сервис поиска недоступен. Проверьте ключ RapidAPI или попробуйте позже.",
    "unavailable": "Не удалось получить данные от сервиса поиска. Попробуйте позже.",
}

MENU_BUTTONS = {
    "🏷 Дешевые отели": "lowprice",
    "⭐ По рейтингу": "guest_rating",
    "🏆 Лучшее предложение": "bestdeal",
    "📜 История": "history",
}


def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(
        KeyboardButton("🏷 Дешевые отели"),
        KeyboardButton("⭐ По рейтингу"),
    )
    markup.row(
        KeyboardButton("🏆 Лучшее предложение"),
        KeyboardButton("📜 История"),
    )
    return markup


def get_state(user_id):
    state = user_states.get(user_id)
    if not state:
        return None
    if time.time() - state.get("ts", 0) > STATE_TTL_SEC:
        user_states.pop(user_id, None)
        return None
    return state


def set_state(user_id, **kwargs):
    state = get_state(user_id) or {}
    state.update(kwargs)
    state["ts"] = time.time()
    user_states[user_id] = state
    return state


def clear_state(user_id):
    user_states.pop(user_id, None)


def touch_user(entity):
    if entity and entity.from_user:
        upsert_user(entity.from_user.id, entity.from_user.username)


def api_error_text(error: HotelApiError) -> str:
    return API_ERROR_MESSAGES.get(error.kind, API_ERROR_MESSAGES["unavailable"])


def hotel_markup(hotel: dict):
    keyboard = InlineKeyboardMarkup()
    added = False
    link = hotel.get("link") or ""
    if is_allowed_booking_url(link):
        keyboard.add(InlineKeyboardButton("Забронировать", url=link.strip()))
        added = True
    maps = maps_url(hotel.get("latitude"), hotel.get("longitude"))
    if maps:
        keyboard.add(InlineKeyboardButton("Показать на карте", url=maps))
        added = True
    return keyboard if added else None


@bot.message_handler(commands=["start", "help"])
def send_welcome(message: Message):
    touch_user(message)
    clear_state(message.from_user.id)
    text = (
        "Привет! Я бот для поиска отелей.\n\n"
        "Выберите команду из меню или используйте:\n"
        "/lowprice — самые дешёвые отели\n"
        "/guest_rating — отели с лучшим рейтингом отзывов\n"
        "/bestdeal — лучшие отзывы при низкой цене, с фильтром диапазона цен\n"
        "/history — история поиска\n"
        "/cancel — отменить текущий поиск"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu())


@bot.message_handler(commands=["cancel"])
def cancel_search(message: Message):
    touch_user(message)
    if get_state(message.from_user.id):
        clear_state(message.from_user.id)
        bot.send_message(message.chat.id, "Поиск отменён. Выберите команду из меню.")
    else:
        bot.send_message(message.chat.id, "Сейчас нет активного поиска.")


@bot.message_handler(func=lambda m: m.text in MENU_BUTTONS)
def handle_menu_buttons(message: Message):
    command = MENU_BUTTONS[message.text]
    message.text = f"/{command}"
    if command == "history":
        get_history(message)
    else:
        start_search(message)


@bot.message_handler(commands=["history"])
def get_history(message: Message):
    touch_user(message)
    uid = str(message.from_user.id)
    history = (
        SearchHistory.select()
        .where(SearchHistory.user_id == uid)
        .order_by(SearchHistory.date_time.desc())
        .limit(10)
    )
    if not history.exists():
        bot.send_message(message.chat.id, "История поиска пуста.")
        return

    blocks = ["📜 <b>Ваши последние запросы:</b>"]
    for item in history:
        blocks.append(
            history_item_html(item.hotel_name, item.price, item.date_time, item.hotel_link)
        )
    bot.send_message(
        message.chat.id,
        "\n\n".join(blocks),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@bot.message_handler(commands=["lowprice", "guest_rating", "bestdeal"])
def start_search(message: Message):
    touch_user(message)
    command = message.text.replace("/", "").split()[0]
    if command not in SORT_BY:
        return
    clear_state(message.from_user.id)
    set_state(message.from_user.id, command=command, step="city")
    bot.send_message(
        message.chat.id,
        "Введите город для поиска (или /cancel для отмены):",
    )


@bot.message_handler(func=lambda m: get_state(getattr(m.from_user, "id", None) or 0) and get_state(m.from_user.id).get("step") == "city" and m.text not in MENU_BUTTONS)
def get_city(message: Message):
    touch_user(message)
    state = get_state(message.from_user.id)
    if not state:
        bot.send_message(message.chat.id, "Сессия поиска истекла. Начните заново через меню или /start.")
        return
    query = sanitize_city_query(message.text or "")
    if not query:
        bot.send_message(
            message.chat.id,
            "Укажите название города до 80 символов, без пустой строки.",
        )
        return
    if not city_limiter.allow(message.from_user.id):
        bot.send_message(message.chat.id, "Слишком много запросов. Подождите минуту и попробуйте снова.")
        return

    bot.send_message(message.chat.id, "🔍 Ищу город...")
    try:
        found = search_city(query)
    except HotelApiError as error:
        bot.send_message(message.chat.id, api_error_text(error))
        return

    if not found:
        bot.send_message(message.chat.id, "Город не найден. Попробуйте ввести название на английском.")
        return

    set_state(
        message.from_user.id,
        dest_id=found["dest_id"],
        dest_type=found["dest_type"],
        city_name=found["name"],
        step="checkin",
    )
    calendar, _step = DetailedTelegramCalendar(calendar_id=1, min_date=datetime.date.today()).build()
    bot.send_message(message.chat.id, "Выберите дату заезда:", reply_markup=calendar)


@bot.callback_query_handler(func=DetailedTelegramCalendar.func(calendar_id=1))
def on_checkin_select(callback):
    touch_user(callback)
    user_id = callback.from_user.id
    state = get_state(user_id)
    if not state or state.get("step") not in {"checkin", "checkout", "price_range"}:
        bot.answer_callback_query(callback.id, "Сессия поиска истекла. Начните заново.")
        return

    result, key, _step = DetailedTelegramCalendar(
        calendar_id=1, min_date=datetime.date.today()
    ).process(callback.data)
    if not result and key:
        bot.edit_message_text(
            "Выберите дату заезда:",
            callback.message.chat.id,
            callback.message.message_id,
            reply_markup=key,
        )
        return
    if not result:
        return
    today = datetime.date.today()
    if result < today or (result - today).days > 365:
        bot.answer_callback_query(callback.id, "Дата заезда не может быть в прошлом или позже чем через год.")
        return

    set_state(user_id, checkin=result, step="checkout")
    bot.edit_message_text(
        f"Дата заезда: {result}",
        callback.message.chat.id,
        callback.message.message_id,
    )
    calendar, _step = DetailedTelegramCalendar(
        calendar_id=2, min_date=result + datetime.timedelta(days=1)
    ).build()
    bot.send_message(callback.message.chat.id, "Выберите дату выезда:", reply_markup=calendar)


@bot.callback_query_handler(func=DetailedTelegramCalendar.func(calendar_id=2))
def on_checkout_select(callback):
    touch_user(callback)
    user_id = callback.from_user.id
    state = get_state(user_id)
    if not state or "checkin" not in state:
        bot.answer_callback_query(callback.id, "Сессия поиска истекла. Начните заново.")
        return

    checkin = state["checkin"]
    result, key, _step = DetailedTelegramCalendar(
        calendar_id=2, min_date=checkin + datetime.timedelta(days=1)
    ).process(callback.data)
    if not result and key:
        bot.edit_message_text(
            "Выберите дату выезда:",
            callback.message.chat.id,
            callback.message.message_id,
            reply_markup=key,
        )
        return
    if not result:
        return
    if not validate_stay_dates(checkin, result):
        bot.answer_callback_query(
            callback.id,
            "Проверьте даты: выезд позже заезда, не больше 90 ночей.",
        )
        return

    set_state(user_id, checkout=result)
    bot.edit_message_text(
        f"Дата выезда: {result}",
        callback.message.chat.id,
        callback.message.message_id,
    )
    if state.get("command") == "bestdeal":
        set_state(user_id, step="price_range")
        bot.send_message(
            callback.message.chat.id,
            "Введите диапазон цен в USD, например 10-100 (или /cancel):",
        )
    else:
        set_state(user_id, step="searching")
        finish_search(callback.message.chat.id, user_id)


@bot.message_handler(func=lambda m: get_state(getattr(m.from_user, "id", None) or 0) and get_state(m.from_user.id).get("step") == "price_range" and m.text not in MENU_BUTTONS)
def get_price(message: Message):
    touch_user(message)
    state = get_state(message.from_user.id)
    if not state:
        bot.send_message(message.chat.id, "Сессия поиска истекла. Начните заново через меню или /start.")
        return
    parsed = parse_price_range(message.text or "")
    if not parsed:
        bot.send_message(
            message.chat.id,
            "Неверный диапазон. Введите два числа через дефис, например 50-150, где первое не больше второго.",
        )
        return
    low, high = parsed
    set_state(message.from_user.id, price_min=low, price_max=high, step="searching")
    finish_search(message.chat.id, message.from_user.id)


def finish_search(chat_id, user_id):
    data = get_state(user_id)
    if not data or not data.get("dest_id") or not data.get("checkin") or not data.get("checkout"):
        bot.send_message(chat_id, "Сессия поиска истекла. Начните заново через меню или /start.")
        clear_state(user_id)
        return
    if not hotel_limiter.allow(user_id):
        bot.send_message(chat_id, "Слишком много запросов. Подождите минуту и попробуйте снова.")
        return

    bot.send_message(chat_id, "⏳ Ищу отели, пожалуйста, подождите...")
    sort_by = SORT_BY.get(data.get("command"), "price")
    try:
        hotels = search_hotels(
            dest_id=data["dest_id"],
            dest_type=data["dest_type"],
            checkin=str(data["checkin"]),
            checkout=str(data["checkout"]),
            sort_by=sort_by,
            price_min=data.get("price_min"),
            price_max=data.get("price_max"),
            limit=5,
        )
    except HotelApiError as error:
        bot.send_message(chat_id, api_error_text(error))
        return

    if not hotels:
        bot.send_message(chat_id, "😔 Ничего не найдено по вашим параметрам.")
        clear_state(user_id)
        return

    for hotel in hotels:
        caption = hotel_caption(hotel)
        markup = hotel_markup(hotel)
        try:
            SearchHistory.create(
                user_id=str(user_id),
                command=data["command"],
                hotel_name=str(hotel.get("name") or "Отель")[:255],
                hotel_link=hotel.get("link") or "",
                price=hotel.get("price"),
            )
        except Exception:
            pass
        photo = hotel.get("photo")
        sent = False
        if photo and is_http_url(photo):
            try:
                bot.send_photo(
                    chat_id,
                    photo,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
                sent = True
            except Exception:
                sent = False
        if not sent:
            bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=markup)

    bot.send_message(chat_id, "✅ Поиск завершен!")
    clear_state(user_id)


if __name__ == "__main__":
    init_app()
    print("Бот запущен...")
    bot.infinity_polling()
