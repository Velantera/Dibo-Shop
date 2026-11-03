import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "shop")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")
if not MONGO_URL:
    raise ValueError("MONGO_URL is not set")

PAYMENT_ACCOUNTS = {
    "telebirr": "Telebirr: 0911XXXXXX (Name: Your Name)",
    "cbe": "CBE: 1000XXXXXXXX (Name: Your Name)",
    "awash": "Awash Bank: 013XXXXXXXXX (Name: Your Name)",
}
