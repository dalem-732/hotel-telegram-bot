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
            return {
                "dest_id": data["data"][0]["dest_id"],
                "dest_type": data["data"][0]["search_type"],
                "name": data["data"][0]["name"]
            }
    except Exception as e:
        print(f"API Error (City): {e}")
    return None

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
        "sort_order": sort_order,
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
                hotel_info = {
                    "id": prop.get("id"),
                    "name": prop.get("name"),
                    "price": prop.get("priceBreakdown", {}).get("grossPrice", {}).get("value", 0),
                    "currency": prop.get("priceBreakdown", {}).get("grossPrice", {}).get("currency", "USD"),
                    "rating": prop.get("reviewScore", 0),
                    "photo": prop.get("photoUrls", [""])[0].replace("square60", "max500"),
                    "link": f"https://www.booking.com/hotel/us/{prop.get('name', '').replace(' ', '-')}.html",
                    "latitude": prop.get("latitude"),
                    "longitude": prop.get("longitude")
                }
                results.append(hotel_info)
        return results
    except Exception as e:
        print(f"API Error (Hotels): {e}")
        return []
