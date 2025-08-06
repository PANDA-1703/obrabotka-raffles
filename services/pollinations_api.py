import aiohttp
import asyncio
import json
import re

from loguru import logger

# вверху модуля
pollinations_semaphore = asyncio.Semaphore(2)


PROMPT_TEMPLATE = """
Ты — парсер Telegram-постов. Для каждого поста из списка верни JSON-объект со следующими полями:

- "source_link" — ссылка на пост (уже указана в объекте, оставь без изменений).
- "end_datetime" — дата окончания розыгрыша, например: "2025-07-23 20:00", если нет — "н/з".
- "prize" — только **главный приз**. Если указано несколько — выбери самый ценный/основной.
- "channels" — **массив** ссылок на Telegram-каналы, на которые нужно подписаться. Ссылки могут быть:
  - `https://t.me/имя`
  - `@имя`
  - `https://t.me/+код` (инвайт-ссылки, **оставляй с плюсом**)
  - Markdown-ссылки, зашитые в слова — их нужно извлечь и вернуть как обычные URL.

Если ссылки не указаны — запиши в `"channels"` строку `"н/з"`.

⚠️ Важно:
- Ответ — **строго JSON-массив без пояснений, без markdown**, без обертки `````json.
- Убедись, что JSON валидный и парсится стандартным парсером.

Посты:
{json_data}
"""


PROXIES = [
    None,
    "http://panda:8F9f2f2f@185.255.179.191:56265",
    "http://J3voRx:wH5YNh@147.45.54.60:9457",
    "http://3KzVwz:7KT0YU@147.45.53.23:9547"
]


def parse_pollinations_response(text: str) -> list:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


async def send_to_pollinations(posts):
    prompt = PROMPT_TEMPLATE.format(json_data=json.dumps(posts, ensure_ascii=False))
    payload = {
        "model": "openai",
        "json_mode": True,
        "messages": [{"role": "user", "content": prompt}]
    }

    async def make_request(proxy_url):
        kwargs = {}
        if proxy_url:
            kwargs["proxy"] = proxy_url
            kwargs["connector"] = aiohttp.TCPConnector(verify_ssl=False)

        async with aiohttp.ClientSession(**kwargs) as session:
            try:
                async with session.post("https://text.pollinations.ai/", json=payload, timeout=120) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        logger.error(f"[pollinations] HTTP {resp.status}: {text}")
                        return None
                    try:
                        text = re.sub(r"^```json|```$", "", text.strip())

                        # Удалим Markdown-обёртку и рекламный хвост
                        text = text.strip()
                        text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
                        text = re.sub(r"```$", "", text, flags=re.MULTILINE)
                        text = re.split(r"(?m)^-{3,}$|^\*\*Sponsor\*\*", text)[0].strip()

                        return parse_pollinations_response(text)
                    except Exception as e:
                        logger.error(f"[pollinations] Ошибка парсинга JSON: {e}")
                        logger.debug(f"[pollinations] Ответ Pollinations:\n{text}")
                        return None
            except Exception as e:
                logger.error(f"[pollinations] Ошибка запроса: {e}")
                return None

    for i, proxy in enumerate(PROXIES):
        logger.info(f"[pollinations] Попытка {i+1} (прокси: {proxy or 'без прокси'})")
        async with pollinations_semaphore:
            result = await make_request(proxy)
        if result:
            return result
        await asyncio.sleep(10)

    return []


