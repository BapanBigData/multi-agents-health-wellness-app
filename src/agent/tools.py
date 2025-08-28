import os
import requests
import httpx
from langchain_core.tools import tool
from typing import Optional
from src.agent.configs import SUPABASE_TABLE, supabase, GEO_KEY



from dotenv import load_dotenv
load_dotenv()


async def get_geocode_locationiq(place: str):
    """Fetch latitude and longitude using LocationIQ API for a given place string."""
    url = "https://us1.locationiq.com/v1/search.php"
    params = {"key": GEO_KEY, "q": place, "format": "json"}
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, params=params)
            data = res.json()
            if data and len(data) > 0:
                print(f"🌍 Geocoded address: {place}")
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"⚠️ Geocoding failed for {place}: {e}")
    return None, None


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
    zip_code: str,
    primary_taxonomy_description: Optional[str] = None,
    entity_type: str = "Organization",
) -> list[dict]:
    """
    Locate healthcare providers or facilities using NPI registry data from Supabase filtered by zip code and specialty.

    Args:
        zip_code (str): Zip code where the provider or facility is located. (Required)
        primary_taxonomy_description (Optional[str]): Partial match on provider's specialty (e.g., 'dentist', 'cardiology').
        entity_type (str): Either 'Organization' or 'Individual'. Default is 'Organization'.

    Returns:
        list[dict]: A list of provider/facility records enriched with latitude and longitude.
    """
    
    try:
        print(f"🔍 Searching for providers in zip code: {zip_code}")
        print(f"📋 Entity type: {entity_type}")
        if primary_taxonomy_description:
            print(f"🏥 Specialty filter: {primary_taxonomy_description}")
        
        # Start building the query - filter by zip_code first for optimal performance
        query = supabase.table(SUPABASE_TABLE).select("*").eq("zip_code", zip_code.strip())
        
        # Filter by entity type
        query = query.eq("entity_type", entity_type)
        
        # Filter by taxonomy description (fuzzy/partial match using ilike for case-insensitive)
        if primary_taxonomy_description:
            # Use ilike for case-insensitive partial matching
            taxonomy_pattern = f"%{primary_taxonomy_description.strip()}%"
            query = query.ilike("primary_taxonomy_description", taxonomy_pattern)
        
        # Execute the query
        response = query.execute()
        
        if not response.data:
            print("❌ No providers found matching the criteria.")
            return []
        
        raw_results = response.data
        print(f"✅ Found {len(raw_results)} provider(s) matching the criteria.")
        
        # Enrich results with geocoding
        enriched_results = []
        for rec in raw_results:
            # Build address string for geocoding
            address_parts = []
            if rec.get('practice_street_address'):
                address_parts.append(rec['practice_street_address'])
            if rec.get('practice_city_name'):
                address_parts.append(rec['practice_city_name'])
            if rec.get('practice_state_name'):
                address_parts.append(rec['practice_state_name'])
            if rec.get('practice_postal_code'):
                address_parts.append(rec['practice_postal_code'])
            
            address = ", ".join(filter(None, address_parts))
            
            # Get coordinates
            lat, lon = await get_geocode_locationiq(address)
            
            # Add coordinates to record
            rec["latitude"] = lat
            rec["longitude"] = lon
            
            enriched_results.append(rec)
        
        print(f"🗺️ Successfully enriched {len(enriched_results)} records with coordinates.")
        return enriched_results

    except Exception as e:
        print(f"❌ Error querying Supabase: {e}")
        return []
    

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

