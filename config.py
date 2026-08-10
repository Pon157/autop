"""Конфигурация бота"""
import os
from dotenv import load_dotenv

load_dotenv()

# === BOT ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_IDS = list(map(int, os.getenv("OWNER_IDS", "123456789").split(",")))

# === CHANNEL ===
FORWARD_CHANNEL_ID = int(os.getenv("FORWARD_CHANNEL_ID", "-1001234567890"))

# === YOOKASSA ===
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
PREMIUM_PRICE = 150

# === DATABASE ===
DB_PATH = os.path.abspath(os.getenv("DB_PATH", "bot_database.db"))

# === TELETHON ===
API_ID = int(os.getenv("API_ID", "0")) if os.getenv("API_ID") else 0
API_HASH = os.getenv("API_HASH", "")
SESSIONS_DIR = os.path.abspath(os.getenv("SESSIONS_DIR", "sessions"))

# === PROXY (только для Telethon-сессий; aiogram-бот использует прямое соединение) ===
PROXY_URL = os.getenv("PROXY_URL", "")


def parse_proxy(proxy_url: str):
    """Парсит URL прокси в формат Telethon."""
    if not proxy_url:
        return None
    from urllib.parse import urlparse
    parsed = urlparse(proxy_url)
    scheme = parsed.scheme.lower()
    host = parsed.hostname
    port = parsed.port or (1080 if scheme in ("socks5", "socks4") else 8080)
    username = parsed.username
    password = parsed.password
    if scheme == "socks5":
        return ("socks5", host, port, True, username, password) if username else ("socks5", host, port)
    elif scheme == "http":
        return ("http", host, port, username, password) if username else ("http", host, port)
    elif scheme == "mtproto":
        secret = parsed.path.lstrip("/") if parsed.path else ""
        return ("mtproto", host, port, secret)
    return None


# === LIMITS ===
FLOOD_WAIT_THRESHOLD = 60
MAX_PREMIUM_CHATS = 10
PREMIUM_SEND_INTERVAL = (15, 20)
DEFAULT_SEND_INTERVAL = (30, 60)
MAX_ACCOUNTS_PER_USER = 0
