import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from telegram_bot_calendar import DetailedTelegramCalendar

import main
from api import HotelApiError
from models import SearchHistory, upsert_user


def test_start_resets_state_and_cancel_clears_it():
    main.set_state(7, command="lowprice", step="city")
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7, username="ann"),
        chat=SimpleNamespace(id=7),
        text="/start",
    )
    with patch.object(main, "touch_user"), patch.object(main.bot, "send_message") as send:
        main.send_welcome(message)
        assert main.get_state(7) is None
        assert "/cancel" in send.call_args.args[1]

    main.set_state(7, command="lowprice", step="city")
    with patch.object(main, "touch_user"), patch.object(main.bot, "send_message") as send:
        main.cancel_search(message)
        assert main.get_state(7) is None
        assert "отменён" in send.call_args.args[1].lower()


def test_state_ttl_expires(monkeypatch):
    monkeypatch.setattr(main, "STATE_TTL_SEC", 10)
    clock = {"now": 1000.0}
    monkeypatch.setattr(main.time, "time", lambda: clock["now"])
    main.set_state(1, step="city")
    assert main.get_state(1)["step"] == "city"
    clock["now"] = 1011.0
    assert main.get_state(1) is None


def test_finish_search_without_state_does_not_crash():
    with patch.object(main.bot, "send_message") as send:
        main.finish_search(99, 99)
        assert "истекла" in send.call_args.args[1]


def test_finish_search_saves_history_by_user_id_and_uses_html(app_db):
    main.set_state(
        555111,
        command="lowprice",
        dest_id="1",
        dest_type="city",
        checkin=datetime.date(2026, 12, 1),
        checkout=datetime.date(2026, 12, 5),
        step="searching",
    )
    hotels = [{
        "name": 'Grand <b>X</b> [Phish](https://evil.example)',
        "rating": 8,
        "price": 12.5,
        "currency": "USD",
        "link": "https://www.booking.com/hotel/it/x.html",
        "photo": "",
        "latitude": 41.9,
        "longitude": 12.5,
    }]
    with patch.object(main, "search_hotels", return_value=hotels), \
         patch.object(main.bot, "send_message") as send, \
         patch.object(main.bot, "send_photo") as send_photo:
        main.finish_search(-100123, 555111)

    rows = list(SearchHistory.select().where(SearchHistory.user_id == "555111"))
    assert len(rows) == 1
    assert rows[0].user_id == "555111"
    assert "Phish" in rows[0].hotel_name
    photo_calls = [c for c in send.call_args_list if c.args[1].startswith("🏨")]
    assert photo_calls
    caption_call = photo_calls[0]
    assert caption_call.kwargs["parse_mode"] == "HTML"
    assert "&lt;b&gt;X&lt;/b&gt;" in caption_call.args[1]
    markup = caption_call.kwargs["reply_markup"]
    assert markup is not None
    send_photo.assert_not_called()
    assert main.get_state(555111) is None


def test_finish_search_surfaces_api_errors_and_keeps_state():
    main.set_state(
        8,
        command="lowprice",
        dest_id="1",
        dest_type="city",
        checkin=datetime.date(2026, 12, 1),
        checkout=datetime.date(2026, 12, 5),
        step="searching",
    )
    with patch.object(main, "search_hotels", side_effect=HotelApiError("rate_limit", 429)), \
         patch.object(main.bot, "send_message") as send:
        main.finish_search(8, 8)
    texts = [c.args[1] for c in send.call_args_list]
    assert any("через минуту" in text for text in texts)
    assert main.get_state(8) is not None


def test_get_city_rate_limit_and_api_errors():
    main.set_state(3, command="lowprice", step="city")
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=3, username="ann"),
        chat=SimpleNamespace(id=3),
        text="Paris",
    )
    with patch.object(main, "touch_user"), \
         patch.object(main.city_limiter, "allow", return_value=False), \
         patch.object(main.bot, "send_message") as send, \
         patch.object(main, "search_city") as search:
        main.get_city(message)
        search.assert_not_called()
        assert "Слишком много запросов" in send.call_args.args[1]

    with patch.object(main, "touch_user"), \
         patch.object(main, "search_city", side_effect=HotelApiError("forbidden", 403)), \
         patch.object(main.bot, "send_message") as send:
        main.get_city(message)
        assert "RapidAPI" in send.call_args.args[1]


def test_get_price_validation():
    main.set_state(4, command="bestdeal", step="price_range", dest_id="1", dest_type="city",
                   checkin=datetime.date(2026, 12, 1), checkout=datetime.date(2026, 12, 5))
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=4, username="ann"),
        chat=SimpleNamespace(id=4),
        text="100-10",
    )
    with patch.object(main, "touch_user"), patch.object(main.bot, "send_message") as send, \
         patch.object(main, "finish_search") as finish:
        main.get_price(message)
        finish.assert_not_called()
        assert "Неверный диапазон" in send.call_args.args[1]

    message.text = "0-80"
    with patch.object(main, "touch_user"), patch.object(main, "finish_search") as finish, \
         patch.object(main.bot, "send_message"):
        main.get_price(message)
        assert main.get_state(4)["price_min"] == 0
        assert main.get_state(4)["price_max"] == 80
        finish.assert_called_once_with(4, 4)


def test_checkout_rejects_library_accepted_past_dates():
    today = datetime.date.today()
    main.set_state(5, command="lowprice", step="checkout", checkin=today,
                   dest_id="1", dest_type="city")
    callback = SimpleNamespace(
        id="cb1",
        data="cbcal_2_s_d_2020_1_20",
        from_user=SimpleNamespace(id=5, username="ann"),
        message=SimpleNamespace(chat=SimpleNamespace(id=5), message_id=10),
    )
    result = datetime.date(2020, 1, 20)
    assert DetailedTelegramCalendar(calendar_id=2, min_date=today).process(callback.data)[0] == result
    with patch.object(main, "touch_user"), \
         patch.object(main.bot, "answer_callback_query") as answer, \
         patch.object(main.bot, "edit_message_text"), \
         patch.object(main, "finish_search") as finish:
        main.on_checkout_select(callback)
        finish.assert_not_called()
        assert main.get_state(5).get("checkout") is None
        assert "даты" in answer.call_args.args[1].lower() or "дат" in answer.call_args.args[1].lower()


def test_calendar_without_state_is_guarded():
    callback = SimpleNamespace(
        id="cb2",
        data="cbcal_1_s_d_2026_12_01",
        from_user=SimpleNamespace(id=6, username="ann"),
        message=SimpleNamespace(chat=SimpleNamespace(id=6), message_id=11),
    )
    with patch.object(main, "touch_user"), patch.object(main.bot, "answer_callback_query") as answer:
        main.on_checkin_select(callback)
        assert "истекла" in answer.call_args.args[1]


def test_require_config_fails_fast(monkeypatch):
    import loader
    monkeypatch.setattr(loader, "BOT_TOKEN", "")
    monkeypatch.setattr(loader, "RAPID_API_KEY", "x")
    with pytest.raises(SystemExit):
        loader.require_config()
    monkeypatch.setattr(loader, "BOT_TOKEN", "t")
    monkeypatch.setattr(loader, "RAPID_API_KEY", "")
    with pytest.raises(SystemExit):
        loader.require_config()
    monkeypatch.setattr(loader, "BOT_TOKEN", "t")
    monkeypatch.setattr(loader, "RAPID_API_KEY", "k")
    loader.require_config()


def test_history_command_reads_by_from_user_id(app_db):
    upsert_user(777, "bob")
    SearchHistory.create(
        user_id="777",
        command="lowprice",
        hotel_name="MyHotel",
        hotel_link="https://www.booking.com/hotel/it/my.html",
        price=30,
    )
    SearchHistory.create(
        user_id="-1001",
        command="lowprice",
        hotel_name="Other",
        hotel_link="https://www.booking.com/hotel/it/other.html",
        price=1,
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=777, username="bob"),
        chat=SimpleNamespace(id=-1001),
        text="/history",
    )
    with patch.object(main, "touch_user"), patch.object(main.bot, "send_message") as send:
        main.get_history(message)
    text = send.call_args.args[1]
    assert "MyHotel" in text
    assert "Other" not in text
    assert send.call_args.kwargs["parse_mode"] == "HTML"

def test_start_search_clears_previous_filters():
    main.set_state(9, command="bestdeal", step="price_range", price_min=10, price_max=20, dest_id="old")
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=9, username="ann"),
        chat=SimpleNamespace(id=9),
        text="/lowprice",
    )
    with patch.object(main, "touch_user"), patch.object(main.bot, "send_message"):
        main.start_search(message)
    state = main.get_state(9)
    assert state["command"] == "lowprice"
    assert state["step"] == "city"
    assert "price_min" not in state
    assert "dest_id" not in state

