from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, MONGO_DB_NAME

_client: AsyncIOMotorClient | None = None
_db = None

def init_db_sync():
    """Call once at startup. Motor is lazy — connection opens on first query."""
    global _client, _db
    _client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    _db = _client[MONGO_DB_NAME]

# ---------- Products ----------

async def add_product(name: str, price: float, description: str, photo_file_id: str, stock: int):
    result = await _db.products.insert_one({
        "name": name,
        "price": price,
        "description": description,
        "photo_file_id": photo_file_id,
        "stock": stock,
        "created_at": datetime.utcnow(),
    })
    return str(result.inserted_id)

async def get_products():
    cursor = _db.products.find({"stock": {"$gt": 0}})
    return await cursor.to_list(length=None)

async def get_product(product_id: str):
    try:
        return await _db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        return None

async def decrement_stock(product_id: str, qty: int = 1):
    await _db.products.update_one(
        {"_id": ObjectId(product_id)},
        {"$inc": {"stock": -qty}}
    )

# ---------- Orders ----------

async def create_order(user_id: int, username: str, items: list, total: float, payment_method: str = "pending"):
    result = await _db.orders.insert_one({
        "user_id": user_id,
        "username": username,
        "items": items,
        "total": total,
        "payment_method": payment_method,
        "status": "pending_payment",
        "created_at": datetime.utcnow(),
    })
    return str(result.inserted_id)

async def get_order(order_id: str):
    try:
        return await _db.orders.find_one({"_id": ObjectId(order_id)})
    except Exception:
        return None

async def update_order_status(order_id: str, status: str):
    await _db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": status, "updated_at": datetime.utcnow()}}
    )

async def update_payment_method(order_id: str, method: str):
    await _db.orders.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"payment_method": method}}
    )

async def get_user_orders(user_id: int):
    cursor = _db.orders.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=20)
