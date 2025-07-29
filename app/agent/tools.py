import os
import requests
import math
import httpx
from langchain_core.tools import tool
from dotenv import load_dotenv

load_dotenv()


async def get_geocode_locationiq(place):
    url = "https://us1.locationiq.com/v1/search.php"
    params = {"key": os.getenv("GEOLOCATION_IQ_API_KEY"), "q": place, "format": "json"}
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        data = res.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
        else:
            return None


async def location_bbox_search(place):
    url = "https://us1.locationiq.com/v1/search.php"
    params = {"key": os.getenv("GEOLOCATION_IQ_API_KEY"), "q": place, "format": "json"}
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        data = res.json()
        if data:
            return data
        else:
            return None


@tool
async def get_health_centers(city: str, query: str = "hospitals") -> list:
    """
    Fetches top health centers (e.g., hospitals, clinics) in a city using the Foursquare API
    and returns them as a structured JSON list.

    Parameters:
        city (str): Name of the city (e.g., 'Kolkata')
        query (str): Type of health centers to search for (e.g., hospitals, clinics)

    Returns:
        list: A list of dictionaries, each containing:
            - name: Health center name
            - categories: List of category names
            - address: Formatted address
            - latitude: latitude of the address 
            - longitude: longitude of the address 
            - phone: Telephone number if available
            - website: Website URL if available
    """
    
    api_key = os.getenv("FOURSQUARE_API_KEY")
    
    if not api_key:
        return [{"error": "Missing FOURSQUARE_API_KEY"}]
    url = "https://places-api.foursquare.com/places/search"
    headers = {"accept": "application/json", "X-Places-Api-Version": "2025-06-17", "authorization": api_key}
    params = {"near": city, "query": query, "limit": 10}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return [{"error": f"Foursquare API error: {response.text}"}]
        results = response.json().get("results", [])
        if not results:
            return [{"message": f"No results found for '{query}' in {city}."}]
        extracted = []
        for place in results:
            address = place['location']['formatted_address']
            lat, lon = await get_geocode_locationiq(address)
            extracted.append({
                "name": place.get("name", "Unknown"),
                "categories": [cat.get("name") for cat in place.get("categories", [])],
                "address": address,
                "latitude": lat,
                "longitude": lon,
                "phone": place.get("tel"),
                "website": place.get("website")
            })
        return extracted
    

@tool
def get_medication_info(ingredient: str) -> dict:
    """
    Retrieves medication label details for a specified active ingredient using the OpenFDA Drug Label API.

    Args:
        ingredient (str): The name of the active ingredient in the medication (e.g., 'paracetamol').

    Returns:
        dict: A dictionary containing key medication details such as usage, warnings, dosage, and ingredients.
            Metadata like disclaimers and API terms are excluded.
            Returns an empty dict if no matching medication is found or if the request fails.
    """
    
    try:
        url = f"https://api.fda.gov/drug/label.json?search=active_ingredient:%22{ingredient}%22&limit=1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Return only the first result if available
        if "results" in data and len(data["results"]) > 0:
            return data["results"][0]
        else:
            return {}
        
    except Exception as e:
        return {"error": str(e)}


@tool
def get_air_quality(zip_code: str) -> dict:
    """
    Fetches current air quality index (AQI) information for a given U.S. ZIP code 
    using the AirNow API.

    Args:
        zip_code (str): A 5-digit U.S. ZIP code (e.g., '90210').

    Returns:
        dict: A dictionary with observed date, area, AQI value, pollutant name, and category.
            Returns an error message if data is unavailable or the request fails.
    """
    
    API_KEY = os.getenv("AIR_QUALITY_API_KEY") 
    url = "https://www.airnowapi.org/aq/observation/zipCode/current/"

    params = {
        "format": "application/json",
        "zipCode": zip_code,
        "distance": 25,
        "API_KEY": API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            return {"message": f"No air quality data found for ZIP code {zip_code}."}

        # Return first pollutant's data
        pollutant = data[0]
        return {
            "area": pollutant["ReportingArea"],
            "state": pollutant["StateCode"],
            "latitude": pollutant["Latitude"],
            "longitude": pollutant["Longitude"],
            "pollutant": pollutant["ParameterName"],
            "aqi": pollutant["AQI"],
            "category": pollutant["Category"]["Name"],
            "observed_date": pollutant["DateObserved"],
            "observed_hour": pollutant["HourObserved"],
            "timezone": pollutant["LocalTimeZone"]
        }

    except Exception as e:
        return {"error": str(e)}
    