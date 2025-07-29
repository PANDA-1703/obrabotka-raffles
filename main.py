import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from loguru import logger
from telethon import TelegramClient

from config import BOT_TOKEN, API_ID, API_HASH
from db.db import init_db, save_lottery
from services.folder_manager import create_invite_folder
from services.pollinations_api import send_to_pollinations
from services.subscriber import subscribe_current_user
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
client = TelegramClient("parser", API_ID, API_HASH)

user_states = {}
user_success_map = {}

message_semaphore = asyncio.Semaphore(3)  # не больше 3 одновременно
pollinations_queue = asyncio.Queue()

logger.add("bot.log", rotation="1 MB")  # лог-файл

reply_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚀 Начать приём")]
    ],
    resize_keyboard=True
)


inline_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ Завершить и обработать", callback_data="finish_collect")],
    [InlineKeyboardButton(text="📁 Создать папку", callback_data="create_folder")]
])


@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    await safe_send_message(msg,"👋 Привет! Готов принимать розыгрыши.", reply_markup=reply_kb)


@dp.message(lambda msg: msg.text == "🚀 Начать приём")
async def start_collect_command(msg: types.Message):
    user_states[msg.from_user.id] = []
    await safe_send_message(msg, "📩 Пересылайте посты с розыгрышами по одному")


def normalize_link(link: str) -> str:
    if link.startswith("https://t.me/"):
        return "@" + link.split("/")[-1].lstrip('+')
    return link


async def safe_send_message(message: types.Message, text: str, **kwargs):
    async with message_semaphore:
        try:
            return await message.answer(text, **kwargs)
        except TelegramRetryAfter as e:
            logger.warning(f"[FloodWait] Telegram просит подождать {e.retry_after} сек...")
            await asyncio.sleep(e.retry_after)
            return await message.answer(text, **kwargs)
        except Exception as e:
            logger.error(f"[safe_send_message] Ошибка при отправке: {e}")


@dp.message()
async def on_forwarded_message(msg: types.Message):
    try:
        user_id = msg.from_user.id
        if user_id not in user_states:
            return

        # Используем html_text — он сохраняет вложенные ссылки
        text = msg.html_text or msg.text or msg.caption
        if not msg.forward_from_chat or not text:
            return await safe_send_message(msg, "⛔ Пересылайте только посты с текстом или подписью")

        channel = msg.forward_from_chat
        source_link = (
            f"https://t.me/{channel.username}/{msg.forward_from_message_id}"
            if channel.username
            else f"https://t.me/c/{channel.id}/{msg.forward_from_message_id}"
        )

        post = {"text": text, "source_link": source_link}

        await safe_send_message(msg, "🧠 Пост поставлен в очередь на обработку…")

        # Кладём в очередь для обработки воркером
        await pollinations_queue.put(([post], msg))

    except asyncio.exceptions.TimeoutError:
        await safe_send_message(msg, "❌ Превышено время ожидания")
    except Exception as e:
        logger.exception(f"❌ Ошибка обработки сообщения: {e}")
        await safe_send_message(msg, "❌ Произошла ошибка при обработке поста.")


@dp.callback_query(lambda c: c.data == "finish_collect")
async def on_finish(callback: CallbackQuery):
    user_id = callback.from_user.id
    channels = user_success_map.get(user_id)
    channels = list(set(channels))
    if not channels:
        return await safe_send_message(callback.message,"❌ Нет собранных постов")

    await safe_send_message(callback.message,f"🔄 Подписываемся на {len(channels)} каналов...")
    result = await subscribe_current_user(
        list(channels),
        user_id,
        lambda text: safe_send_message(callback.message, text)
    )
    user_success_map[user_id] = result["successful"]

    all_channels = result['successful']
    chunk_size = 50
    chunks = [all_channels[i:i+chunk_size] for i in range(0, len(all_channels), chunk_size)]

    await safe_send_message(
        callback.message,f"✅ Успешно: {len(result['successful'])}, ❌ Ошибки: {len(result['failed'])}:\n{result['failed']}"
    )
    for chunk in chunks:
        await safe_send_message(callback.message,"📋\n" + "\n".join(chunk))
    user_states.pop(user_id, None)
    return None


@dp.callback_query(lambda c: c.data == "create_folder")
async def on_create_folder(callback: CallbackQuery):
    user_id = callback.from_user.id
    channels = user_success_map.get(user_id)
    if not channels:
        return await safe_send_message(callback.message,"❌ Нет успешных подписок")

    await safe_send_message(callback.message,"📁 Создаю папку...")
    result = await create_invite_folder(channels, user_id)
    await safe_send_message(callback.message,f"✅ {result}")

    del user_success_map[user_id]
    user_states.pop(user_id, None)
    return None


async def pollinations_worker():
    while True:
        posts, message = await pollinations_queue.get()
        try:
            result = await send_to_pollinations(posts)
            if not result:
                await safe_send_message(message, "❌ Не удалось обработать посты")
                continue

            for item in result:
                await save_lottery(item)

                # Обработка списка каналов
                chs = item.get("channels")
                if isinstance(chs, list):
                    chs = [normalize_link(c.strip()) for c in chs if isinstance(c, str) and c.strip() != "н/з"]
                elif isinstance(chs, str):
                    chs = [normalize_link(c.strip()) for c in chs.split(",") if c.strip() != "н/з"]
                else:
                    chs = []

                # 🆕 Если каналов не найдено — добавим канал, из которого переслали пост
                if not chs and message.forward_from_chat:
                    source_chat = message.forward_from_chat
                    if source_chat.username:
                        chs = [f"https://t.me/{source_chat.username}"]
                    else:
                        chs = [f"https://t.me/c/{source_chat.id}"]

                # Обновление карты найденных каналов
                existing = user_success_map.setdefault(message.from_user.id, set())
                existing.update(chs)

                await safe_send_message(
                    message,
                    f"✅ Сохранено\n📢 Каналов найдено: {len(chs)}.\n{chs}",
                    reply_markup=inline_kb
                )

        except Exception as e:
            logger.exception(f"[pollinations_worker] Ошибка: {e}")
        finally:
            pollinations_queue.task_done()


async def main():
    logger.info("Бот запущен...")
    await init_db()
    asyncio.create_task(pollinations_worker())  # запустить воркер
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
