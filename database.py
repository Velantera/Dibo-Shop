import aiosqlite
import json

DB_PATH = "shop.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT,
                photo_file_id TEXT,
                stock INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                items_json TEXT,
                total REAL,
                payment_method TEXT,
                status TEXT DEFAULT 'pending_payment',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def get_products():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, name, price, description, photo_file_id, stock FROM products WHERE stock > 0") as cursor:
            return await cursor.fetchall()

async def create_order(user_id, username, items, total, payment_method):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO orders (user_id, username, items_json, total, payment_method, status) VALUES (?, ?, ?, ?, ?, 'pending_payment')",
            (user_id, username, json.dumps(items), total, payment_method)
        )
        order_id = cursor.lastrowid
        await db.commit()
        return order_id

async def update_order_status(order_id, status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        await db.commit()

async def get_order(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cursor:
            return await cursor.fetchone()
