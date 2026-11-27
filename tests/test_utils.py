import html
from datetime import date, datetime, timedelta

from utils import (
    CITY_QUERY_MAX_LEN,
    RateLimiter,
    TtlCache,
    fallback_hotel_url,
    history_item_html,
    hotel_caption,
    is_allowed_booking_url,
    is_http_url,
    maps_url,
    parse_price_range,
    pick_destination,
    sanitize_city_query,
    valid_coords,
    validate_stay_dates,
)


def test_booking_url_allowlist_rejects_injection_and_other_hosts():
    assert is_allowed_booking_url("https://www.booking.com/hotel/it/rome.html")
    assert is_allowed_booking_url("https://booking.com/searchresults.html?dest_id=1")
    assert is_allowed_booking_url("https://secure.booking.com/book.html")
    assert is_allowed_booking_url("https://r.booking.com/hotel/x")
    assert not is_allowed_booking_url("http://www.booking.com/hotel/it/rome.html")
    assert not is_allowed_booking_url("https://evil.example/phish")
    assert not is_allowed_booking_url("https://www.booking.com.evil.example/x")
    assert not is_allowed_booking_url("https://evil.example/phish) [ok](https://evil.example/2")
    assert not is_allowed_booking_url("javascript:alert(1)")
    assert not is_allowed_booking_url("https://www.booking.com/hotel/x.html) [x](http://evil.example")
    assert not is_allowed_booking_url("")
    assert not is_allowed_booking_url(None)


def test_hotel_caption_escapes_html_and_markdown_payloads():
    caption = hotel_caption({
        "name": 'Grand <b>X</b> *Hotel*_x_ [Phish](https://evil.example)',
        "rating": '8.5<script>',
        "price": 99.9,
        "currency": "USD",
    })
    assert "<b>X</b>" not in caption
    assert "&lt;b&gt;X&lt;/b&gt;" in caption
    assert "https://evil.example" in caption
    assert "[Phish](" in caption
    assert caption.startswith("🏨 <b>")
    assert "99.90 USD" in caption
    assert "<script>" not in caption


def test_history_item_html_drops_unsafe_links_and_escapes_name():
    unsafe = history_item_html(
        "Grand *Hotel* [Phish](https://evil.example)",
        99.9,
        datetime(2026, 3, 27, 20, 0, 0),
        "https://evil.example/phish) [ok](https://evil.example/2",
    )
    assert "Ссылка недоступна" in unsafe
    assert "<a href" not in unsafe
    assert "[Phish](" in unsafe

    safe = history_item_html(
        "Nice Inn",
        10,
        datetime(2026, 3, 27, 20, 0, 0),
        "https://www.booking.com/hotel/it/nice.html",
    )
    assert '<a href="https://www.booking.com/hotel/it/nice.html">Ссылка</a>' in safe
    assert "10.00 USD" in safe


def test_maps_url_rejects_injected_coordinates():
    assert maps_url("1", "2").endswith("query=1.0,2.0")
    assert maps_url("0", "0) [x](https://evil.example") is None
    assert maps_url("91", "0") is None
    assert valid_coords("x", "y") is None


def test_parse_price_range_edges():
    assert parse_price_range("10-100") == (10, 100)
    assert parse_price_range("0-100") == (0, 100)
    assert parse_price_range("10 - 20") == (10, 20)
    assert parse_price_range("100-10") is None
    assert parse_price_range("-5-20") is None
    assert parse_price_range("10-20-30") is None
    assert parse_price_range("abc") is None
    assert parse_price_range("1e2-3") is None
    assert parse_price_range("0-1000001") is None


def test_validate_stay_dates_rejects_past_and_too_long():
    today = date(2026, 11, 27)
    assert validate_stay_dates(today, today + timedelta(days=2), today=today)
    assert not validate_stay_dates(date(2020, 1, 15), date(2020, 1, 20), today=today)
    assert not validate_stay_dates(today, today, today=today)
    assert not validate_stay_dates(today, today + timedelta(days=91), today=today)
    assert not validate_stay_dates(today + timedelta(days=366), today + timedelta(days=367), today=today)


def test_sanitize_city_query_and_pick_city_type():
    assert sanitize_city_query("  Paris  ") == "Paris"
    assert sanitize_city_query("x" * 4000) is None
    assert sanitize_city_query("x" * CITY_QUERY_MAX_LEN) == "x" * CITY_QUERY_MAX_LEN
    assert sanitize_city_query("   ") is None
    items = [
        {"dest_id": "999", "search_type": "landmark", "name": "Tower"},
        {"dest_id": "1", "search_type": "CITY", "name": "Paris"},
    ]
    assert pick_destination(items)["dest_id"] == "1"
    assert pick_destination([items[0]])["dest_id"] == "999"
    assert pick_destination([]) is None


def test_fallback_hotel_url_uses_hotel_dest_and_name_not_ss_id_only():
    url = fallback_hotel_url(42, "Nice Inn", "2026-12-01", "2026-12-02")
    assert url.startswith("https://www.booking.com/searchresults.ru.html?")
    assert "dest_type=hotel" in url
    assert "dest_id=42" in url
    assert "ss=Nice+Inn" in url
    assert "checkin=2026-12-01" in url
    assert is_allowed_booking_url(url)


def test_rate_limiter_and_ttl_cache(monkeypatch):
    limiter = RateLimiter(max_calls=2, window_sec=60)
    assert limiter.allow("u1")
    assert limiter.allow("u1")
    assert not limiter.allow("u1")
    assert limiter.allow("u2")

    cache = TtlCache(ttl_sec=10, max_size=2)
    cache.set("a", "1")
    cache.set("b", "2")
    assert cache.get("a") == "1"
    cache.set("c", "3")
    assert cache.get("a") is None
    assert cache.get("c") == "3"

    clock = {"now": 100.0}
    monkeypatch.setattr("utils.time.monotonic", lambda: clock["now"])
    cache = TtlCache(ttl_sec=5, max_size=8)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    clock["now"] = 106.0
    assert cache.get("k") is None


def test_is_http_url():
    assert is_http_url("https://cf.bstatic.com/x.jpg")
    assert is_http_url("http://example.com/x.jpg")
    assert not is_http_url("javascript:alert(1)")
    assert not is_http_url("")
    assert not is_http_url(None)
