import asyncio
import os
import re

from loguru import logger
from telethon import TelegramClient, types
from telethon.errors import FloodWaitError
from telethon.errors.rpcerrorlist import UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import InputChannel

from config import API_ID, API_HASH
from telethon.errors import FloodWaitError


from telethon.errors import FloodWaitError, UsernameNotOccupiedError, UsernameInvalidError
from telethon.tl.functions.messages import ImportChatInviteRequest

entity_cache = {}


async def resolve_channel(client, link: str):
    link = link.strip()
    if not link:
        return None

    # Нормализуем ссылку
    if link.startswith("http"):
        match = re.search(r"t\.me/([\w\d_@+-]+)", link)
        if not match:
            logger.warning(f"[resolve_channel] Невалидная ссылка: {link}")
            return None
        link = match.group(1)

    # Удалим лишний '@'
    if link.startswith("@"):
        link = link[1:]

    # Пропускаем странные короткие строки (часто это мусор)
    if len(link) < 5:
        logger.warning(f"[resolve_channel] Слишком короткая ссылка: {link}")
        return None

    # Проверка кеша
    if link in entity_cache:
        return entity_cache[link]

    try:
        if link.startswith("+"):
            # Ссылка-приглашение
            updates = await client(ImportChatInviteRequest(link[1:]))
            entity = updates.chats[0] if updates.chats else None
        else:
            # Username
            entity = await client.get_entity(link)

        entity_cache[link] = entity
        return entity

    except FloodWaitError as e:
        logger.warning(f"[resolve_channel] FloodWait {e.seconds} сек для {link}")
        await asyncio.sleep(e.seconds + 3)
        return await resolve_channel(client, link)

    except (UsernameNotOccupiedError, UsernameInvalidError):
        logger.warning(f"[resolve_channel] Не найден пользователь: {link}")
        return None

    except Exception as e:
        logger.error(f"[resolve_channel] Ошибка для {link}: {e}")
        return None


async def subscribe_current_user(channels, user_id, notify=None):
    session_name = f"session_{user_id}"
    session_file = f"{session_name}.session"

    if not os.path.exists(session_file):
        raise Exception("Аккаунт не авторизован")

    client = TelegramClient(session_file, API_ID, API_HASH)
    successful, failed = [], []

    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise Exception("Аккаунт не авторизован")

        for ch in channels:
            try:
                entity = await resolve_channel(client, ch)
                if not entity:
                    failed.append(ch)
                    continue

                if isinstance(entity, types.Channel):
                    # Добавляем в успешные в любом случае (независимо от подписки)
                    successful.append(ch)

                    # Подписываемся только если пользователь ещё не подписан
                    if getattr(entity, "left", False):
                        await client(JoinChannelRequest(InputChannel(entity.id, entity.access_hash)))
                        await asyncio.sleep(2)

            except FloodWaitError as e:
                logger.warning(f"FloodWait: {e.seconds}s on {ch}")
                if notify:
                    logger.error(f"⚠️ FloodWait {e.seconds}s: {ch}")
                    await notify(f"⏳ FloodWait {e.seconds}s: {ch}")
                await asyncio.sleep(e.seconds + 5)

            except Exception as e:
                failed.append(ch)
                if notify:
                    logger.error(f"⚠️ Ошибка на {ch}:\n{e}")
                    await notify(f"⚠️ Ошибка на {ch}:\n{e}")
    finally:
        await client.disconnect()

    return {"successful": successful, "failed": failed}

