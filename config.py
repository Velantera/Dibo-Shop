import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop")

# Clean up IDs to prevent crashes from quotes or spaces
def get_clean_id(env_var: str) -> int:
    val = os.getenv(env_var, "0")
    # Remove quotes, spaces, and weird characters
    clean_val = val.replace('"', '').replace("'", "").replace(" ", "")
    try:
        return int(clean_val)
    except ValueError:
        return 0

ADMIN_GROUP_ID = get_clean_id("ADMIN_GROUP_ID")
CHANNEL_ID = get_clean_id("CHANNEL_ID")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")
if not MONGO_URL:
    raise ValueError("MONGO_URL is not set")

PAYMENT_ACCOUNTS = {
    "telebirr": "Telebirr: 0911XXXXXX (Name: Your Name)",
    "cbe": "CBE: 1000XXXXXXXX (Name: Your Name)",
    "awash": "Awash Bank: 013XXXXXXXXX (Name: Your Name)",
}
