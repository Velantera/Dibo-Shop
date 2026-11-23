import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")
MONGO_URL = os.getenv("MONGO_URL", "").strip().strip('"').strip("'")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop").strip().strip('"').strip("'")

def get_clean_id(env_var: str, default: int = 0) -> int:
    value = os.getenv(env_var, str(default))
    value = value.strip().replace('"', '').replace("'", '').replace(" ", "")
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# Keep OWNER_ID as the primary owner for compatibility with existing modules.
OWNER_ID = get_clean_id("OWNER_ID")
OWNER2_ID = get_clean_id("OWNER2_ID")

# All authorized admin Telegram user IDs. Remove unset/duplicate IDs.
OWNER_IDS = tuple(dict.fromkeys(uid for uid in (OWNER_ID, OWNER2_ID) if uid))

def is_admin(user_id: int) -> bool:
    return user_id in OWNER_IDS

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
