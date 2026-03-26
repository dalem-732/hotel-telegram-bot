import requests
import json
from loader import RAPID_API_KEY

HEADERS = {
    "X-RapidAPI-Key": RAPID_API_KEY,
    "X-RapidAPI-Host": "booking-com15.p.rapidapi.com"
}

def search_city(city_name: str) -> dict | None:
    """Ищет destination_id города."""
    url = "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchDestination"
    querystring = {"query": city_name}

    try:
        response = requests.get(url, headers=HEADERS, params=querystring, timeout=10)
        data = response.json()
        if data.get("status") and data.get("data"):
            # Берем первый результат
            return {
                "dest_id": data["data"][0]["dest_id"],
                "dest_type": data["data"][0]["search_type"],
                "name": data["data"][0]["name"]
            }
    except Exception as e:
        print(f"API Error (City): {e}")
    return None

def get_hotel_url(hotel_id: int, checkin: str, checkout: str) -> str:
    """
    Получает реальный URL страницы отеля на Booking.com через getHotelDetails.
    Возвращает URL или пустую строку при ошибке.
    """
    url = "https://booking-com15.p.rapidapi.com/api/v1/hotels/getHotelDetails"
    querystring = {
        "hotel_id": str(hotel_id),
        "arrival_date": checkin,
        "departure_date": checkout,
        "adults": "1",
        "currency_code": "USD",
        "languagecode": "ru"
    }
    try:
        response = requests.get(url, headers=HEADERS, params=querystring, timeout=10)
        data = response.json()
        if data.get("status") and data.get("data"):
            d = data["data"]
            # Выводим все ключи верхнего уровня для отладки
            print(f"[DEBUG] getHotelDetails keys: {list(d.keys())}")
            # Ищем url во вложенных полях
            found_url = (
                d.get("url") or
                d.get("hotel_url") or
                d.get("pageUrl") or
                d.get("booking_url") or
                d.get("hotelUrl") or
                ""
            )
            print(f"[DEBUG] found_url = {found_url!r}")
            return found_url
        else:
            print(f"[DEBUG] getHotelDetails bad response: {data}")
    except Exception as e:
        print(f"API Error (HotelDetails id={hotel_id}): {e}")
    return ""


def search_hotels(
    dest_id: str, 
    dest_type: str, 
    checkin: str, 
    checkout: str, 
    sort_order: str, 
    price_min: int = None, 
    price_max: int = None,
    limit: int = 5
) -> list:
    """
    Ищет отели по параметрам.
    checkin/checkout format: YYYY-MM-DD
    """
    url = "https://booking-com15.p.rapidapi.com/api/v1/hotels/searchHotels"
    
    querystring = {
        "dest_id": dest_id,
        "search_type": dest_type,
        "arrival_date": checkin,
        "departure_date": checkout,
        "adults": "1",
        "sort_order": sort_order, # PRICE, CLASS_DESCENDING, DISTANCE_FROM_LANDMARK
        "page_number": "1",
        "currency_code": "USD"
    }

    if price_min and price_max:
        querystring["price_min"] = price_min
        querystring["price_max"] = price_max

    try:
        response = requests.get(url, headers=HEADERS, params=querystring, timeout=15)
        data = response.json()
        
        results = []
        if data.get("status") and data.get("data") and data["data"].get("hotels"):
            hotels = data["data"]["hotels"][:limit]
            
            for hotel in hotels:
                prop = hotel.get("property", {})
                # Формируем красивый словарь
                hotel_id = prop.get("id")
                # Пробуем взять URL прямо из ответа searchHotels
                api_url = hotel.get("url") or prop.get("url") or ""
                if api_url and api_url.startswith("http"):
                    link = api_url
                else:
                    # Делаем отдельный запрос getHotelDetails для получения реального URL
                    link = get_hotel_url(hotel_id, checkin, checkout)
                    if not link:
                        # Крайний fallback: поисковая страница отеля по ID (всегда работает)
                        link = f"https://www.booking.com/searchresults.ru.html?ss={hotel_id}&selected_currency=USD"

                hotel_info = {
                    "id": hotel_id,
                    "name": prop.get("name"),
                    "price": prop.get("priceBreakdown", {}).get("grossPrice", {}).get("value", 0),
                    "currency": prop.get("priceBreakdown", {}).get("grossPrice", {}).get("currency", "USD"),
                    "rating": prop.get("reviewScore", 0),
                    "photo": prop.get("photoUrls", [""])[0].replace("square60", "max500"), # Улучшаем качество фото
                    "link": link,
                    "latitude": prop.get("latitude"),
                    "longitude": prop.get("longitude")
                }
                results.append(hotel_info)
        return results
    except Exception as e:
        print(f"API Error (Hotels): {e}")
        return []
