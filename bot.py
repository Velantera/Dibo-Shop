import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN
from database import init_db_sync
from handlers import user, admin

logging.basicConfig(level=logging.INFO)

async def main():
    init_db_sync()  # Motor client — lazy connection
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
    dp = Dispatcher()
    dp.include_router(user.router)
    dp.include_router(admin.router)

    logging.info("Bot starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
