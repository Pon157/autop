"""Конфигурация бота"""
import os
from dotenv import load_dotenv

load_dotenv()

# === BOT ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_IDS = list(map(int, os.getenv("OWNER_IDS", "123456789").split(",")))  # Несколько owner_id через запятую

# === CHANNEL ===
FORWARD_CHANNEL_ID = int(os.getenv("FORWARD_CHANNEL_ID", "-1001234567890"))  # Канал для пересылки постов

# === YOOKASSA ===
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
PREMIUM_PRICE = 150  # рублей в месяц

# === DATABASE ===
DB_PATH = os.getenv("DB_PATH", "bot_database.db")

# === TELETHON ===
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSIONS_DIR = "sessions"

# === LIMITS ===
FLOOD_WAIT_THRESHOLD = 60  # секунд — порог предупреждения
MAX_PREMIUM_CHATS = 10  # макс. чатов для премиум (без Telegram Premium)
PREMIUM_SEND_INTERVAL = (15, 20)  # секунд между постами для премиум
DEFAULT_SEND_INTERVAL = (30, 60)  # секунд между постами для обычной рассылки
MAX_ACCOUNTS_PER_USER = 0  # 0 = только owner добавляет аккаунты
