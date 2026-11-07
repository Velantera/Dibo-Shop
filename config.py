import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop")

# Clean up IDs to prevent crashes from quotes or spaces
def get_clean_id(env_var: str) -> int:
    val = os.getenv(env_var, "0")
    clean_val = val.replace('"', '').replace("'", "").replace(" ", "")
    try:
        return int(clean_val)
    except ValueError:
        return 0

# NEW: Your personal Telegram ID
OWNER_ID = get_clean_id("OWNER_ID") 
ADMIN_GROUP_ID = get_clean_id("ADMIN_GROUP_ID")
CHANNEL_ID = get_clean_id("CHANNEL_ID")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")
if not MONGO_URL:
    raise ValueError("MONGO_URL is not set")
if not OWNER_ID:
    raise ValueError("OWNER_ID is not set. Add it to your .env file!")

PAYMENT_ACCOUNTS = {
    "telebirr": "Telebirr: 0927982723 (Name: Dibora Diriba)",
    "cbe": "CBE: 1000146782012 (Name: Dibora Diriba)",
}
