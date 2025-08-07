from urllib.parse import quote_plus
import os
from dotenv import load_dotenv

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