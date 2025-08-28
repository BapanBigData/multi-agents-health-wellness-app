from urllib.parse import quote_plus
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Safe encoding for MongoDB URI
safe_username = quote_plus(os.getenv("MONGO_USERNAME", ""))
safe_password = quote_plus(os.getenv("MONGO_PASSWORD", ""))
MONGO_URI = (
    f"mongodb+srv://{safe_username}:{safe_password}"
    f"@happmongocluster.mongocluster.cosmos.azure.com/"
    f"?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000"
)

DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GEO_KEY = os.getenv("GEOLOCATION_IQ_API_KEY")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)