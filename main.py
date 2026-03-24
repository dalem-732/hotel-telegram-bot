import datetime
from telebot import custom_filters
from telebot.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP

from loader import bot
from api import search_city, search_hotels
from models import User, SearchHistory

user_states = {}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message: Message):
    User.get_or_create(user_id=str(message.from_user.id), defaults={'username': message.from_user.username})
    text = (
        "Привет! Я бот для поиска отелей.\n\n"
        "Доступные команды:\n"
        "/lowprice — Топ самых дешевых отелей\n"
        "/guest_rating — Топ отелей по рейтингу\n"
        "/bestdeal — Лучшее предложение (цена/качество)\n"
        "/history — История поиска"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['history'])
def get_history(message: Message):
    uid = str(message.from_user.id)
    history = SearchHistory.select().where(SearchHistory.user_id == uid).order_by(SearchHistory.date_time.desc()).limit(10)
    
    if not history.exists():
        bot.send_message(message.chat.id, "История поиска пуста.")
        return

    text = "📜 **Ваши последние запросы:**\n\n"
    for item in history:
        text += (
            f"🏨 {item.hotel_name}\n"
            f"💰 {item.price} USD\n"
            f"📅 {item.date_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"🔗 [Ссылка]({item.hotel_link})\n"
            f"---------------------------\n"
        )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=['lowprice', 'guest_rating', 'bestdeal'])
def start_search(message: Message):
    command = message.text.replace('/', '')
    user_states[message.chat.id] = {
        "command": command,
        "step": "city"
    }
    bot.send_message(message.chat.id, "Введите город для поиска:")

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") == "city")
def get_city(message: Message):
    city = message.text
    bot.send_message(message.chat.id, "🔍 Ищу город...")
    
    found = search_city(city)
    if not found:
        bot.send_message(message.chat.id, "Город не найден. Попробуйте ввести название на английском.")
        return

    user_states[message.chat.id]["dest_id"] = found["dest_id"]
    user_states[message.chat.id]["dest_type"] = found["dest_type"]
    user_states[message.chat.id]["city_name"] = found["name"]
    user_states[message.chat.id]["step"] = "checkin"
    
    calendar, step = DetailedTelegramCalendar(calendar_id=1, min_date=datetime.date.today()).build()
    bot.send_message(message.chat.id, f"Выберите дату заезда:", reply_markup=calendar)

@bot.callback_query_handler(func=DetailedTelegramCalendar.func(calendar_id=1))
def on_checkin_select(c):
    result, key, step = DetailedTelegramCalendar(calendar_id=1, min_date=datetime.date.today()).process(c.data)
    if not result and key:
        bot.edit_message_text(f"Выберите дату заезда:", c.message.chat.id, c.message.message_id, reply_markup=key)
    elif result:
        user_states[c.message.chat.id]["checkin"] = result
        bot.edit_message_text(f"Дата заезда: {result}", c.message.chat.id, c.message.message_id)
        
        calendar, step = DetailedTelegramCalendar(calendar_id=2, min_date=result + datetime.timedelta(days=1)).build()
        bot.send_message(c.message.chat.id, f"Выберите дату выезда:", reply_markup=calendar)

@bot.callback_query_handler(func=DetailedTelegramCalendar.func(calendar_id=2))
def on_checkout_select(c):
    checkin = user_states.get(c.message.chat.id, {}).get("checkin", datetime.date.today())
    
    result, key, step = DetailedTelegramCalendar(calendar_id=2, min_date=checkin + datetime.timedelta(days=1)).process(c.data)
    if not result and key:
        bot.edit_message_text(f"Выберите дату выезда:", c.message.chat.id, c.message.message_id, reply_markup=key)
    elif result:
        user_states[c.message.chat.id]["checkout"] = result
        bot.edit_message_text(f"Дата выезда: {result}", c.message.chat.id, c.message.message_id)
        
        if user_states[c.message.chat.id]["command"] == "bestdeal":
            user_states[c.message.chat.id]["step"] = "price_range"
            bot.send_message(c.message.chat.id, "Введите диапазон цен (например: 10-100) в USD:")
        else:
            finish_search(c.message)

@bot.message_handler(func=lambda m: user_states.get(m.chat.id, {}).get("step") == "price_range")
def get_price(message: Message):
    try:
        low, high = map(int, message.text.split('-'))
        user_states[message.chat.id]["price_min"] = low
        user_states[message.chat.id]["price_max"] = high
        finish_search(message)
    except ValueError:
        bot.send_message(message.chat.id, "Неверный формат. Введите два числа через дефис (например: 50-150).")

def finish_search(message: Message):
    chat_id = message.chat.id
    data = user_states.get(chat_id)
    
    bot.send_message(chat_id, "⏳ Ищу отели, пожалуйста подождите...")
    
    sort_map = {
        "lowprice": "PRICE",
        "guest_rating": "CLASS_DESCENDING",
        "bestdeal": "DISTANCE_FROM_LANDMARK"
    }
    sort_order = sort_map.get(data["command"], "PRICE")
    
    hotels = search_hotels(
        dest_id=data["dest_id"],
        dest_type=data["dest_type"],
        checkin=str(data["checkin"]),
        checkout=str(data["checkout"]),
        sort_order=sort_order,
        price_min=data.get("price_min"),
        price_max=data.get("price_max"),
        limit=5
    )
    
    if not hotels:
        bot.send_message(chat_id, "😔 Ничего не найдено по вашим параметрам.")
        user_states.pop(chat_id, None)
        return

    for hotel in hotels:
        caption = (
            f"🏨 *{hotel['name']}*\n"
            f"⭐ Рейтинг: {hotel['rating']}\n"
            f"💰 Цена: {hotel['price']} {hotel['currency']}\n"
            f"📍 [Показать на карте](https://www.google.com/maps/search/?api=1&query={hotel['latitude']},{hotel['longitude']})\n\n"
            f"[Забронировать]({hotel['link']})"
        )
        
        SearchHistory.create(
            user_id=str(chat_id),
            command=data["command"],
            hotel_name=hotel['name'],
            hotel_link=hotel['link'],
            price=hotel['price']
        )
        
        if hotel['photo']:
            try:
                bot.send_photo(chat_id, hotel['photo'], caption=caption, parse_mode="Markdown")
            except:
                bot.send_message(chat_id, caption, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, caption, parse_mode="Markdown")
            
    bot.send_message(chat_id, "✅ Поиск завершен!")
    user_states.pop(chat_id, None)

if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
