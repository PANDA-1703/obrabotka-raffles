import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PROXY_URL = os.getenv("PROXY")
DB_PATH = os.getenv("DB_PATH", "lotteries.db")