from datetime import datetime
from bson import ObjectId
from pymongo import ReturnDocument
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


async def update_payment_method(order_id: str, method: str):
    try:
        await _db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {"payment_method": method}}
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


async def update_order_fields(order_id: str, update_data: dict):
    try:
        result = await _db.orders.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": {**update_data, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0 or result.matched_count > 0
    except Exception as e:
        print(f"Error updating order fields: {e}")
        return False


async def claim_delivery_schedule(order_id: str, days: int, delivery_text: str):
    """Atomically let exactly one admin select delivery days for an eligible order.

    Returns the updated order for the winner, or None if another admin already
    selected a schedule (or the order is not eligible anymore).
    """
    try:
        return await _db.orders.find_one_and_update(
            {
                "_id": ObjectId(order_id),
                "status": {"$in": ["paid", "cod_pending"]},
                "$or": [
                    {"delivery_days": {"$exists": False}},
                    {"delivery_days": None},
                ],
            },
            {
                "$set": {
                    "delivery_days": int(days),
                    "delivery_time_text": delivery_text,
                    "delivery_selected_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
    except Exception as e:
        print(f"Error claiming delivery schedule for order {order_id}: {e}")
        return None


# ==========================================
# USERS (For Broadcast / Reminders)
# ==========================================
async def save_user(user_id: int, first_name: str, username: str):
    try:
        await _db.users.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "first_name": first_name,
                    "username": username,
                    "last_seen": datetime.utcnow()
                },
                "$setOnInsert": {"joined_at": datetime.utcnow()}
            },
            upsert=True
        )
    except Exception as e:
        print(f"Error saving user: {e}")


async def get_all_users():
    cursor = _db.users.find({})
    return await cursor.to_list(length=None)
