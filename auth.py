import asyncio

from loguru import logger
from telethon.sync import TelegramClient
from config import API_ID, API_HASH


async def login_as_main_user():
    session_name = input("Имя файла сессии (например, session_123456789): ").strip()
    phone = input("Введите номер телефона с +7...: ").strip()

    client = TelegramClient(session_name, API_ID, API_HASH)

    async with client:
        await client.start(phone=phone)
        me = await client.get_me()
        logger.info(f"✅ Авторизован как: {me.first_name} (@{me.username})")
        logger.info(f"📁 Сессия сохранена в: {session_name}.session")


if __name__ == '__main__':
    asyncio.run(login_as_main_user())
