import json

import aiosqlite
from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lotteries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_link TEXT UNIQUE,
                end_datetime TEXT,
                prize TEXT,
                channels TEXT
            )
        """)
        await db.commit()


async def save_lottery(item):
    async with aiosqlite.connect(DB_PATH) as db:
        channels = item.get("channels", [])
        if isinstance(channels, list):
            channels = ", ".join(str(c) for c in channels)
        elif isinstance(channels, dict):
            channels = json.dumps(channels, ensure_ascii=False)
        elif not isinstance(channels, str):
            channels = str(channels)

        prize = item.get("prize", "н/з")
        if isinstance(prize, list):
            # Преобразуем список словарей в строки, если надо
            if all(isinstance(p, dict) for p in prize):
                prize = ", ".join(json.dumps(p, ensure_ascii=False) for p in prize)
            else:
                prize = ", ".join(str(p) for p in prize)
        elif isinstance(prize, dict):
            prize = json.dumps(prize, ensure_ascii=False)
        elif not isinstance(prize, str):
            prize = str(prize)

        await db.execute("""
            INSERT OR IGNORE INTO lotteries (source_link, end_datetime, prize, channels)
            VALUES (?, ?, ?, ?)
        """, (
            item.get("source_link"),
            item.get("end_datetime", "н/з"),
            prize,
            channels
        ))
        await db.commit()





async def get_all_lotteries():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM lotteries") as cur:
            rows = await cur.fetchall()
            return [
                {
                    "source_link": row[1],
                    "end_datetime": row[2],
                    "prize": row[3],
                    "channels": row[4],
                } for row in rows
            ]
