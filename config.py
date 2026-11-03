import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))  # Your admin group ID (negative number)
# Payment account information (customize according to actual situation)
PAYMENT_ACCOUNTS = {
    "telebirr": "Telebirr: 0911XXXXXX (Name: Your Name)",
    "cbe": "CBE: 1000XXXXXXXX (Name: Your Name)",
    "awash": "Awash Bank: 013XXXXXXXXX (Name: Your Name)",
}
