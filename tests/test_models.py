from models import User, SearchHistory, upsert_user


def test_history_is_keyed_by_user_id_not_chat_id(app_db):
    group_chat_id = -1001234567890
    user_id = 555111
    SearchHistory.create(
        user_id=str(group_chat_id),
        command="lowprice",
        hotel_name="GroupHotel",
        hotel_link="https://www.booking.com/hotel/it/g.html",
        price=10,
    )
    SearchHistory.create(
        user_id=str(user_id),
        command="lowprice",
        hotel_name="PrivateHotel",
        hotel_link="https://www.booking.com/hotel/it/p.html",
        price=20,
    )
    by_user = list(SearchHistory.select().where(SearchHistory.user_id == str(user_id)))
    by_chat = list(SearchHistory.select().where(SearchHistory.user_id == str(group_chat_id)))
    assert [item.hotel_name for item in by_user] == ["PrivateHotel"]
    assert [item.hotel_name for item in by_chat] == ["GroupHotel"]


def test_upsert_user_updates_username(app_db):
    first = upsert_user(42, "old_name")
    assert first.username == "old_name"
    assert User.select().count() == 1
    updated = upsert_user(42, "new_name")
    assert updated.id == first.id
    assert User.get(User.user_id == "42").username == "new_name"
