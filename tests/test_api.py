from unittest.mock import MagicMock, patch

import pytest

import api
from api import HotelApiError, search_city, search_hotels, get_hotel_url, SORT_BY
from utils import is_allowed_booking_url


def _json_response(payload, status=200):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    return response


def test_sort_by_values_match_commands():
    assert SORT_BY["lowprice"] == "price"
    assert SORT_BY["guest_rating"] == "bayesian_review_score"
    assert SORT_BY["bestdeal"] == "review_score_and_price"


def test_search_hotels_uses_sort_by_and_keeps_price_min_zero():
    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = dict(params)
        return _json_response({"status": True, "data": {"hotels": []}})

    with patch.object(api.requests, "get", side_effect=fake_get):
        search_hotels("1", "city", "2026-12-01", "2026-12-02", "price", price_min=0, price_max=100)

    assert "sort_order" not in captured["params"]
    assert captured["params"]["sort_by"] == "price"
    assert captured["params"]["price_min"] == 0
    assert captured["params"]["price_max"] == 100
    assert captured["url"].endswith("/api/v1/hotels/searchHotels")


def test_empty_photo_urls_do_not_fail_entire_search():
    payload = {
        "status": True,
        "data": {
            "hotels": [
                {
                    "url": "https://evil.example/phish) [x](http://evil.example",
                    "property": {
                        "id": 1,
                        "name": "Grand *Hotel*_italic_ [Phish](https://evil.example)",
                        "priceBreakdown": {"grossPrice": {"value": 99.9, "currency": "USD"}},
                        "reviewScore": 8.5,
                        "photoUrls": [],
                        "latitude": "1",
                        "longitude": "2) [x](https://evil.example",
                        "url": "javascript:alert(1)",
                    },
                },
                {
                    "property": {
                        "id": 2,
                        "name": "Nice Inn",
                        "priceBreakdown": {"grossPrice": {"value": 10, "currency": "USD"}},
                        "reviewScore": 9,
                        "photoUrls": ["https://cf.bstatic.com/square60/pic.jpg"],
                        "latitude": 41.9,
                        "longitude": 12.5,
                        "url": "https://www.booking.com/hotel/it/nice.html",
                    }
                },
            ]
        },
    }
    with patch.object(api.requests, "get", return_value=_json_response(payload)):
        results = search_hotels("123", "city", "2026-12-01", "2026-12-02", "price")

    assert len(results) == 2
    assert results[0]["photo"] == ""
    assert results[0]["link"].startswith("https://www.booking.com/searchresults.ru.html?")
    assert "dest_id=1" in results[0]["link"]
    assert results[0]["link"].startswith("https://www.booking.com/")
    assert is_allowed_booking_url(results[0]["link"])
    assert results[1]["photo"] == "https://cf.bstatic.com/max500/pic.jpg"
    assert results[1]["link"] == "https://www.booking.com/hotel/it/nice.html"


def test_missing_photo_urls_and_http_url_without_allowlist():
    payload = {
        "status": True,
        "data": {
            "hotels": [{
                "property": {
                    "id": 42,
                    "name": "Nice Inn",
                    "priceBreakdown": {"grossPrice": {"value": 10, "currency": "USD"}},
                    "reviewScore": 9,
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "url": "http://evil.example/booking",
                }
            }]
        },
    }
    with patch.object(api.requests, "get", return_value=_json_response(payload)) as mocked:
        results = search_hotels("123", "city", "2026-12-01", "2026-12-02", "price")
    assert results[0]["photo"] == ""
    assert results[0]["link"].startswith("https://www.booking.com/")
    assert results[0]["link"].startswith("https://www.booking.com/")
    assert is_allowed_booking_url(results[0]["link"])
    urls = [call.args[0] for call in mocked.call_args_list]
    assert any("getHotelDetails" in url for url in urls)


def test_http_errors_surface_as_hotel_api_error():
    with patch.object(api.requests, "get", return_value=_json_response({"message": "no"}, status=403)):
        with pytest.raises(HotelApiError) as forbidden:
            search_city("Paris")
        assert forbidden.value.kind == "forbidden"
        assert forbidden.value.status == 403

    with patch.object(api.requests, "get", return_value=_json_response({}, status=429)):
        with pytest.raises(HotelApiError) as limited:
            search_hotels("1", "city", "2026-12-01", "2026-12-02", "price")
        assert limited.value.kind == "rate_limit"

    with patch.object(api.requests, "get", return_value=_json_response({}, status=500)):
        with pytest.raises(HotelApiError) as unavailable:
            search_city("Paris")
        assert unavailable.value.kind == "unavailable"


def test_search_city_prefers_city_and_rejects_too_long_query():
    payload = {
        "status": True,
        "data": [
            {"dest_id": "999", "search_type": "landmark", "name": "Something unexpected"},
            {"dest_id": "1", "search_type": "city", "name": "Paris"},
        ],
    }
    with patch.object(api.requests, "get", return_value=_json_response(payload)) as mocked:
        found = search_city("x" * 4000)
        assert found is None
        mocked.assert_not_called()
        found = search_city("  Paris  ")
        assert found == {"dest_id": "1", "dest_type": "city", "name": "Paris"}
        assert mocked.call_args.kwargs["params"]["query"] == "Paris"


def test_get_hotel_url_and_cache_ignore_non_booking_and_errors():
    details = {
        "status": True,
        "data": {"url": "https://www.booking.com/hotel/it/rome.html"},
    }
    with patch.object(api.requests, "get", return_value=_json_response(details)) as mocked:
        url = get_hotel_url(10, "2026-12-01", "2026-12-02")
        assert url == "https://www.booking.com/hotel/it/rome.html"

        payload = {
            "status": True,
            "data": {"hotels": [{
                "property": {
                    "id": 10,
                    "name": "Rome Hotel",
                    "priceBreakdown": {"grossPrice": {"value": 1, "currency": "USD"}},
                }
            }]},
        }
        mocked.return_value = _json_response(payload)
        details_before = sum(1 for c in mocked.call_args_list if "getHotelDetails" in c.args[0])
        results = search_hotels("1", "city", "2026-12-01", "2026-12-02", "price")
        assert results[0]["link"] == "https://www.booking.com/hotel/it/rome.html"
        details_after = sum(1 for c in mocked.call_args_list if "getHotelDetails" in c.args[0])
        assert details_after == details_before

    with patch.object(api.requests, "get", return_value=_json_response({}, status=429)):
        assert get_hotel_url(11, "2026-12-01", "2026-12-02") == ""


def test_broken_hotel_card_is_skipped_not_all_results():
    payload = {
        "status": True,
        "data": {
            "hotels": [
                "bad-row",
                {
                    "property": {
                        "id": 3,
                        "name": "Ok",
                        "priceBreakdown": {"grossPrice": {"value": 5, "currency": "USD"}},
                        "url": "https://www.booking.com/hotel/it/ok.html",
                    }
                },
            ]
        },
    }
    with patch.object(api.requests, "get", return_value=_json_response(payload)):
        results = search_hotels("1", "city", "2026-12-01", "2026-12-02", "price")
    assert len(results) == 1
    assert results[0]["name"] == "Ok"
