import html
import time
from collections import defaultdict, deque
from datetime import date
from urllib.parse import urlencode, urlparse


CITY_QUERY_MAX_LEN = 80
CITY_TYPES = {"city", "cities"}
MAX_PRICE = 1_000_000
MAX_STAY_DAYS = 90
MAX_CHECKIN_AHEAD_DAYS = 365
ALLOWED_BOOKING_HOSTS = {
    "booking.com",
    "www.booking.com",
    "secure.booking.com",
}


class RateLimiter:
    def __init__(self, max_calls: int, window_sec: int):
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._hits = defaultdict(deque)

    def allow(self, key) -> bool:
        now = time.monotonic()
        queue = self._hits[str(key)]
        while queue and now - queue[0] >= self.window_sec:
            queue.popleft()
        if len(queue) >= self.max_calls:
            return False
        queue.append(now)
        return True


class TtlCache:
    def __init__(self, ttl_sec: int, max_size: int = 512):
        self.ttl_sec = ttl_sec
        self.max_size = max_size
        self._data = {}

    def get(self, key):
        item = self._data.get(key)
        if not item:
            return None
        value, expires_at = item
        if time.monotonic() >= expires_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key, value):
        now = time.monotonic()
        expired = [stored for stored, (_, expires_at) in self._data.items() if now >= expires_at]
        for stored in expired:
            self._data.pop(stored, None)
        if len(self._data) >= self.max_size and key not in self._data:
            oldest = next(iter(self._data))
            self._data.pop(oldest, None)
        self._data[key] = (value, now + self.ttl_sec)


def is_http_url(url) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_allowed_booking_url(url) -> bool:
    if not url or not isinstance(url, str):
        return False
    candidate = url.strip()
    forbidden = (" ", "\n", "\r", "\t", '"', "'", "<", ">", "`", ")")
    if any(char in candidate for char in forbidden):
        return False
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in ALLOWED_BOOKING_HOSTS:
        return True
    return host.endswith(".booking.com")


def valid_coords(lat, lon):
    try:
        latitude = float(lat)
        longitude = float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def maps_url(lat, lon):
    coords = valid_coords(lat, lon)
    if not coords:
        return None
    latitude, longitude = coords
    return f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"


def fallback_hotel_url(hotel_id, name, checkin, checkout) -> str:
    params = {
        "dest_type": "hotel",
        "checkin": checkin,
        "checkout": checkout,
        "selected_currency": "USD",
        "lang": "ru",
    }
    if hotel_id not in (None, ""):
        params["dest_id"] = str(hotel_id)
    if name:
        params["ss"] = str(name)
    return "https://www.booking.com/searchresults.ru.html?" + urlencode(params)


def parse_price_range(text: str):
    if not text or "-" not in text:
        return None
    left, separator, right = text.partition("-")
    if not separator or "-" in right:
        return None
    try:
        low = int(left.strip())
        high = int(right.strip())
    except ValueError:
        return None
    if low < 0 or high < 0 or low > high or high > MAX_PRICE:
        return None
    return low, high


def validate_stay_dates(checkin, checkout, today=None) -> bool:
    if today is None:
        today = date.today()
    if not isinstance(checkin, date) or not isinstance(checkout, date):
        return False
    if checkin < today:
        return False
    if checkout <= checkin:
        return False
    if (checkin - today).days > MAX_CHECKIN_AHEAD_DAYS:
        return False
    if (checkout - checkin).days > MAX_STAY_DAYS:
        return False
    return True


def sanitize_city_query(text: str):
    if not text:
        return None
    query = " ".join(text.split())
    if not query or len(query) > CITY_QUERY_MAX_LEN:
        return None
    return query


def pick_destination(items):
    if not items:
        return None
    for item in items:
        if str(item.get("search_type") or "").lower() in CITY_TYPES:
            return item
    return items[0]


def hotel_caption(hotel: dict) -> str:
    name = html.escape(str(hotel.get("name") or "Отель"))
    raw_rating = hotel.get("rating")
    rating = html.escape(str(raw_rating if raw_rating not in (None, "") else "—"))
    try:
        price = float(hotel.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    currency = html.escape(str(hotel.get("currency") or "USD"))
    return (
        f"🏨 <b>{name}</b>\n"
        f"⭐ Рейтинг: {rating}\n"
        f"💰 Цена: {price:.2f} {currency}"
    )


def history_item_html(hotel_name, price, date_time, hotel_link) -> str:
    name = html.escape(str(hotel_name or "Отель"))
    try:
        price_value = float(price or 0)
        price_text = f"{price_value:.2f}"
    except (TypeError, ValueError):
        price_text = html.escape(str(price or "—"))
    when = html.escape(date_time.strftime("%Y-%m-%d %H:%M") if date_time else "")
    if is_allowed_booking_url(hotel_link):
        href = html.escape(hotel_link.strip(), quote=True)
        link = f'<a href="{href}">Ссылка</a>'
    else:
        link = "Ссылка недоступна"
    return (
        f"🏨 {name}\n"
        f"💰 {price_text} USD\n"
        f"📅 {when}\n"
        f"🔗 {link}"
    )
