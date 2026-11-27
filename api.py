import requests

from utils import (
    TtlCache,
    fallback_hotel_url,
    is_allowed_booking_url,
    is_http_url,
    pick_destination,
    sanitize_city_query,
)

RAPID_API_HOST = "booking-com15.p.rapidapi.com"
SORT_BY = {
    "lowprice": "price",
    "guest_rating": "bayesian_review_score",
    "bestdeal": "review_score_and_price",
}

_url_cache = TtlCache(ttl_sec=3600, max_size=512)


class HotelApiError(Exception):
    def __init__(self, kind: str, status: int | None = None):
        self.kind = kind
        self.status = status
        super().__init__(kind)


def _headers():
    import os
    return {
        "X-RapidAPI-Key": os.getenv("RAPID_API_KEY") or "",
        "X-RapidAPI-Host": RAPID_API_HOST,
    }


def _request_json(url: str, params: dict, timeout: int) -> dict:
    try:
        response = requests.get(url, headers=_headers(), params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise HotelApiError("unavailable") from exc
    if response.status_code == 429:
        raise HotelApiError("rate_limit", 429)
    if response.status_code in (401, 403):
        raise HotelApiError("forbidden", response.status_code)
    if response.status_code >= 400:
        raise HotelApiError("unavailable", response.status_code)
    try:
        data = response.json()
    except ValueError as exc:
        raise HotelApiError("unavailable", response.status_code) from exc
    if not isinstance(data, dict):
        raise HotelApiError("unavailable", response.status_code)
    return data


def _destination_payload(item: dict) -> dict | None:
    if not item:
        return None
    dest_id = item.get("dest_id")
    dest_type = item.get("search_type")
    name = item.get("name")
    if dest_id in (None, "") or not dest_type:
        return None
    return {
        "dest_id": str(dest_id),
        "dest_type": str(dest_type),
        "name": name or "",
    }


def _first_photo(prop: dict) -> str:
    urls = prop.get("photoUrls")
    if not isinstance(urls, list) or not urls:
        return ""
    first = urls[0]
    if not isinstance(first, str) or not first:
        return ""
    photo = first.replace("square60", "max500")
    return photo if is_http_url(photo) else ""


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_link(hotel_id, name, checkin, checkout, raw_url: str) -> str:
    if is_allowed_booking_url(raw_url):
        return raw_url.strip()
    cached = _url_cache.get((str(hotel_id), checkin, checkout))
    if cached:
        return cached
    details_url = ""
    if hotel_id not in (None, ""):
        details_url = get_hotel_url(hotel_id, checkin, checkout)
    if is_allowed_booking_url(details_url):
        link = details_url.strip()
        _url_cache.set((str(hotel_id), checkin, checkout), link)
        return link
    return fallback_hotel_url(hotel_id, name, checkin, checkout)


def search_city(city_name: str) -> dict | None:
    query = sanitize_city_query(city_name)
    if not query:
        return None
    url = f"https://{RAPID_API_HOST}/api/v1/hotels/searchDestination"
    data = _request_json(url, {"query": query}, timeout=10)
    items = data.get("data") if data.get("status") else None
    if not isinstance(items, list):
        return None
    return _destination_payload(pick_destination(items))


def get_hotel_url(hotel_id, checkin: str, checkout: str) -> str:
    cache_key = (str(hotel_id), checkin, checkout)
    cached = _url_cache.get(cache_key)
    if cached:
        return cached
    url = f"https://{RAPID_API_HOST}/api/v1/hotels/getHotelDetails"
    params = {
        "hotel_id": str(hotel_id),
        "arrival_date": checkin,
        "departure_date": checkout,
        "adults": "1",
        "currency_code": "USD",
        "languagecode": "ru",
    }
    try:
        data = _request_json(url, params, timeout=10)
    except HotelApiError:
        return ""
    if not data.get("status") or not isinstance(data.get("data"), dict):
        return ""
    payload = data["data"]
    for key in ("url", "hotel_url", "pageUrl", "booking_url", "hotelUrl"):
        value = payload.get(key)
        if is_allowed_booking_url(value):
            link = value.strip()
            _url_cache.set(cache_key, link)
            return link
    return ""


def search_hotels(
    dest_id: str,
    dest_type: str,
    checkin: str,
    checkout: str,
    sort_by: str,
    price_min: int = None,
    price_max: int = None,
    limit: int = 5,
) -> list:
    url = f"https://{RAPID_API_HOST}/api/v1/hotels/searchHotels"
    params = {
        "dest_id": dest_id,
        "search_type": dest_type,
        "arrival_date": checkin,
        "departure_date": checkout,
        "adults": "1",
        "sort_by": sort_by,
        "page_number": "1",
        "currency_code": "USD",
    }
    if price_min is not None and price_max is not None:
        params["price_min"] = price_min
        params["price_max"] = price_max

    data = _request_json(url, params, timeout=15)
    results = []
    if not (data.get("status") and isinstance(data.get("data"), dict)):
        return results
    hotels = data["data"].get("hotels") or []
    if not isinstance(hotels, list):
        return results

    for hotel in hotels[:limit]:
        try:
            if not isinstance(hotel, dict):
                continue
            prop = hotel.get("property") or {}
            if not isinstance(prop, dict):
                prop = {}
            hotel_id = prop.get("id")
            name = prop.get("name") or "Отель"
            raw_url = hotel.get("url") or prop.get("url") or ""
            link = _resolve_link(hotel_id, name, checkin, checkout, raw_url)
            results.append({
                "id": hotel_id,
                "name": name,
                "price": _to_float(
                    (prop.get("priceBreakdown") or {}).get("grossPrice", {}).get("value", 0)
                ),
                "currency": (prop.get("priceBreakdown") or {}).get("grossPrice", {}).get("currency") or "USD",
                "rating": prop.get("reviewScore", 0),
                "photo": _first_photo(prop),
                "link": link,
                "latitude": prop.get("latitude"),
                "longitude": prop.get("longitude"),
            })
        except (TypeError, ValueError, KeyError, IndexError):
            continue
    return results
