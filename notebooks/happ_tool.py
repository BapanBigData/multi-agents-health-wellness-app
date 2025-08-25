# supabase_provider_lookup.py

from typing import Optional
from langchain.tools import tool
import os
from dotenv import load_dotenv
import httpx
import asyncio
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEO_KEY = os.getenv("GEOLOCATION_IQ_API_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


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


@tool
async def lookup_provider_info(
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


# For testing/debugging
if __name__ == "__main__":
    async def test():
        # Test with zip code and specialty
        query =  {
        "zip_code": "77477",
        "primary_taxonomy_description": "emergency",
        "entity_type": "Organization"
    }
        results = await lookup_provider_info.ainvoke(query)
        
        print(f"\n📊 Test Results:")
        print(results[:5])
        # for i, result in enumerate(results[:3], 1):  # Show first 3 results
        #     print(f"\n{i}. {result.get('provider_org_name_legal', 'N/A')}")
        #     print(f"   NPI: {result.get('npi', 'N/A')}")
        #     print(f"   Type: {result.get('entity_type', 'N/A')}")
        #     print(f"   Specialty: {result.get('primary_taxonomy_description', 'N/A')}")
        #     print(f"   Address: {result.get('practice_street_address', 'N/A')}")
        #     print(f"   City: {result.get('practice_city_name', 'N/A')}, {result.get('practice_state_name', 'N/A')} {result.get('practice_postal_code', 'N/A')}")
        #     print(f"   Coordinates: {result.get('latitude', 'N/A')}, {result.get('longitude', 'N/A')}")

    asyncio.run(test())