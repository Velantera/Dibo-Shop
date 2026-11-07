from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, MONGO_DB_NAME

_client: AsyncIOMotorClient | None = None
_db = None

def init_db_sync():
    global _client, _db
    _client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    _db = _client[MONGO_DB_NAME]

# ==========================================
# PRODUCTS
# ==========================================
async def add_product(name: str, price: float, description: str, photo_file_id: str, stock: int, sizes: list):
    result = await _db.products.insert_one({
        "name": name,
        "price": price,
        "description": description,
        "photo_file_id": photo_file_id,
        "stock": stock,
        "sizes": sizes,
        "channel_message_id": None,
        "created_at": datetime.utcnow(),
    })
    return str(result.inserted_id)

async def get_products():
    cursor = _db.products.find({"stock": {"$gt": 0}})
    return await cursor.to_list(length=None)

async def get_all_products():
    cursor = _db.products.find({})
    return await cursor.to_list(length=None)

async def get_product(product_id: str):
    try:
        return await _db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        return None

async def update_product(product_id: str, update_data: dict):
    try:
        await _db.products.update_one({"_id": ObjectId(product_id)}, {"$set": update_data})
        return True
    except Exception:
        return False

async def delete_product(product_id: str):
    try:
        await _db.products.delete_one({"_id": ObjectId(product_id)})
        return True
    except Exception:
        return False

async def decrement_stock(product_id: str, qty: int = 1):
    try:
        await _db.products.update_one({"_id": ObjectId(product_id)}, {"$inc": {"stock": -qty}})
    except Exception:
        pass

async def increment_stock(product_id: str, qty: int = 1):
    try:
        await _db.products.update_one({"_id": ObjectId(product_id)}, {"$inc": {"stock": qty}})
    except Exception:
        pass

# ==========================================
# ORDERS
# ==========================================
async def create_order(user_id: int, username: str, items: list, total: float, payment_method: str = "pending", language: str = "en"):
    result = await _db.orders.insert_one({
        "user_id": user_id,
        "username": username,
        "items": items,
        "total": total,
        "payment_method": payment_method,
        "status": "pending_details",
        "customer_name": "",
        "phone_number": "",
        "address": "",
        "language": language,
        "created_at": datetime.utcnow(),
    })
    return str(result.inserted_id)

async def get_order(order_id: str):
    try:
        return await _db.orders.find_one({"_id": ObjectId(order_id)})
    except Exception:
        return None

async def update_order_details(order_id: str, name: str, phone: str, address: str):
    try:
        await _db.orders.update_one(
            {"_id": ObjectId(order_id)}, 
            {"$set": {"customer_name": name, "phone_number": phone, "address": address}}
        )
    except Exception:
        pass

async def update_order_status(order_id: str, status: str):
    try:
        await _db.orders.update_one(
            {"_id": ObjectId(order_id)}, 
            {"$set": {"status": status, "updated_at": datetime.utcnow()}}
        )
    except Exception:
        pass

async def get_user_orders(user_id: int):
    cursor = _db.orders.find(
        {"user_id": user_id, "status": {"$ne": "cancelled"}}
    ).sort("created_at", -1).limit(20)
    return await cursor.to_list(length=20)

async def get_all_orders():
    cursor = _db.orders.find({}).sort("created_at", -1).limit(50)
    return await cursor.to_list(length=50)
