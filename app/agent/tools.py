import os
import requests
import httpx
from langchain_core.tools import tool
from typing import Optional
import pymongo
import certifi
from pymongo.errors import ConnectionFailure
from app.agent.configs import MONGO_URI, DB_NAME, COLLECTION_NAME

import warnings

# Suppress CosmosDB compatibility warnings from pymongo
warnings.filterwarnings(
    "ignore",
    message="You appear to be connected to a CosmosDB cluster.*",
    category=UserWarning
)



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
async def get_health_centers(
    practice_city_name: str,
    primary_taxonomy_description: Optional[str] = None,
    entity_type: str = "Organization",
    npi_number: Optional[int] = None,
    provider_first_name: Optional[str] = None,
    provider_last_name_legal: Optional[str] = None,
    practice_state_name: Optional[str] = "TX",
    practice_street_address: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Locate healthcare providers or facilities using NPI registry data filtered by location, specialty, or name.

    This tool fetches provider or organization records from a MongoDB collection containing NPPES NPI data.
    It allows filtering by city, state, provider name, taxonomy (specialty), street address, and more.
    The results are further enriched with geographic coordinates (latitude, longitude) using LocationIQ
    for integration with maps or proximity-based queries.

    Args:
        practice_city_name (str): City where the provider or facility is located. (Required)
        primary_taxonomy_description (Optional[str]): Partial match on provider's specialty (e.g., 'cardiology').
        entity_type (str): Either 'Organization' or 'Individual'. Default is 'Organization'.
        npi_number (Optional[int]): Exact NPI number for direct lookup.
        provider_first_name (Optional[str]): First name of the provider (for individuals).
        provider_last_name_legal (Optional[str]): Last name of the provider (for individuals).
        practice_state_name (Optional[str]): State abbreviation (e.g., 'CA', 'NY').
        practice_street_address (Optional[str]): Partial or full street address.
        limit (int): Number of records to return. Default is 20.

    Returns:
        list[dict]: A list of provider/facility records enriched with latitude and longitude, ready for geospatial mapping.
    """

    
    query = {
        "practice_city_name": {"$regex": f"^{practice_city_name.strip()}$", "$options": "i"},
        "entity_type": entity_type
    }

    if npi_number:
        query["npi_number"] = npi_number

    if provider_first_name:
        query["provider_first_name"] = {"$regex": f"^{provider_first_name.strip()}$", "$options": "i"}

    if provider_last_name_legal:
        query["provider_last_name_legal"] = {"$regex": f"^{provider_last_name_legal.strip()}$", "$options": "i"}

    if practice_state_name:
        query["practice_state_name"] = practice_state_name.strip().upper()

    if practice_street_address:
        query["practice_street_address"] = {"$regex": f".*{practice_street_address.strip()}.*", "$options": "i"}

    if primary_taxonomy_description:
        query["primary_taxonomy_description"] = {"$regex": f".*{primary_taxonomy_description.strip()}.*", "$options": "i"}

    try:
        client = pymongo.MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        print("✅ Connected to MongoDB.")

        raw_results = list(collection.find(query, {"_id": 0}).limit(limit))
        print(f"🔍 Found {len(raw_results)} result(s).")

        enriched_results = []
        for rec in raw_results:
            address = f"{rec.get('practice_street_address', '')}, {rec.get('practice_city_name', '')}, {rec.get('practice_state_name', '')}"
            lat, lon = await get_geocode_locationiq(address)
            rec["latitude"] = lat
            rec["longitude"] = lon
            enriched_results.append(rec)

        return enriched_results

    except ConnectionFailure as conn_fail:
        print(f"❌ MongoDB connection failed. {conn_fail}")
        return []
    except Exception as e:
        print(f"❌ Error: {e}")
        return []
    finally:
        if client:
            client.close()
            print("🔌 MongoDB connection closed.")
    

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

