"""Работа с базой данных (SQLite)"""
import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import config


class Database:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_db(self):
        """Инициализация таблиц"""
        with self._connect() as conn:
            cursor = conn.cursor()

            # Аккаунты
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone TEXT UNIQUE NOT NULL,
                    session_name TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    flood_wait_until INTEGER DEFAULT 0,
                    last_used INTEGER DEFAULT 0,
                    load_count INTEGER DEFAULT 0,
                    daily_sent INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_premium INTEGER DEFAULT 0,
                    premium_user_id INTEGER DEFAULT NULL,
                    premium_until TIMESTAMP DEFAULT NULL
                )
            """)

            # Пользователи
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    is_premium INTEGER DEFAULT 0,
                    premium_until TIMESTAMP DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Посты на модерации
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    channel_message_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    selected_accounts TEXT DEFAULT '[]',
                    selected_folders TEXT DEFAULT '[]',
                    selected_chats TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Папки чатов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    chat_ids TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Логи рассылки
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS send_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL,
                    account_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'success',
                    error_msg TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Платежи
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    payment_id TEXT UNIQUE NOT NULL,
                    amount REAL NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    paid_at TIMESTAMP DEFAULT NULL
                )
            """)

            # Настройки (API_ID, API_HASH и др.)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            conn.commit()

    # === SETTINGS ===
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

    def get_api_credentials(self) -> tuple:
        """Возвращает (api_id, api_hash) из БД или .env"""
        api_id = self.get_setting("api_id")
        api_hash = self.get_setting("api_hash")
        if api_id and api_hash:
            return int(api_id), api_hash
        return config._API_ID, config._API_HASH

    # === ACCOUNTS ===
    def add_account(self, phone: str, session_name: str) -> bool:
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO accounts (phone, session_name) VALUES (?, ?)",
                    (phone, session_name)
                )
                return True
        except sqlite3.IntegrityError:
            return False

    def get_accounts(self, status: Optional[str] = None) -> List[Dict]:
        with self._connect() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM accounts WHERE status = ?", (status,))
            else:
                cursor.execute("SELECT * FROM accounts")
            return [dict(row) for row in cursor.fetchall()]

    def get_account(self, account_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_account_status(self, account_id: int, status: str, flood_wait: int = 0):
        with self._connect() as conn:
            cursor = conn.cursor()
            flood_until = int(datetime.now().timestamp()) + flood_wait if flood_wait > 0 else 0
            cursor.execute(
                "UPDATE accounts SET status = ?, flood_wait_until = ? WHERE id = ?",
                (status, flood_until, account_id)
            )

    def increment_account_load(self, account_id: int):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE accounts SET load_count = load_count + 1, last_used = ? WHERE id = ?",
                (int(datetime.now().timestamp()), account_id)
            )

    def reset_daily_stats(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE accounts SET daily_sent = 0")

    # === USERS ===
    def add_user(self, user_id: int, username: str = None, first_name: str = None):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR IGNORE INTO users (user_id, username, first_name)
                   VALUES (?, ?, ?)""",
                (user_id, username, first_name)
            )

    def get_user(self, user_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_premium(self, user_id: int, until: datetime):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?",
                (until.isoformat(), user_id)
            )

    def is_premium_active(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user or not user.get("is_premium"):
            return False
        if user.get("premium_until"):
            until = datetime.fromisoformat(user["premium_until"])
            return until > datetime.now()
        return False

    # === POSTS ===
    def create_pending_post(self, user_id: int, message_id: int) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO pending_posts (user_id, message_id) VALUES (?, ?)",
                (user_id, message_id)
            )
            return cursor.lastrowid

    def get_post(self, post_id: int) -> Optional[Dict]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_posts WHERE id = ?", (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_post_status(self, post_id: int, status: str, channel_message_id: int = None):
        with self._connect() as conn:
            cursor = conn.cursor()
            if channel_message_id:
                cursor.execute(
                    "UPDATE pending_posts SET status = ?, channel_message_id = ? WHERE id = ?",
                    (status, channel_message_id, post_id)
                )
            else:
                cursor.execute(
                    "UPDATE pending_posts SET status = ? WHERE id = ?",
                    (status, post_id)
                )

    def update_post_selection(self, post_id: int, accounts: str = None, folders: str = None, chats: str = None):
        with self._connect() as conn:
            cursor = conn.cursor()
            if accounts:
                cursor.execute("UPDATE pending_posts SET selected_accounts = ? WHERE id = ?", (accounts, post_id))
            if folders:
                cursor.execute("UPDATE pending_posts SET selected_folders = ? WHERE id = ?", (folders, post_id))
            if chats:
                cursor.execute("UPDATE pending_posts SET selected_chats = ? WHERE id = ?", (chats, post_id))

    def get_user_posts(self, user_id: int) -> List[Dict]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pending_posts WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    # === FOLDERS ===
    def add_folder(self, user_id: int, name: str, chat_ids: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_folders (user_id, name, chat_ids) VALUES (?, ?, ?)",
                (user_id, name, chat_ids)
            )
            return cursor.lastrowid

    def get_folders(self, user_id: int) -> List[Dict]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chat_folders WHERE user_id = ?", (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def delete_folder(self, folder_id: int):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_folders WHERE id = ?", (folder_id,))

    # === PAYMENTS ===
    def add_payment(self, user_id: int, payment_id: str, amount: float):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO payments (user_id, payment_id, amount) VALUES (?, ?, ?)",
                (user_id, payment_id, amount)
            )

    def update_payment(self, payment_id: str, status: str):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE payments SET status = ?, paid_at = ? WHERE payment_id = ?",
                (status, datetime.now().isoformat() if status == "succeeded" else None, payment_id)
            )

    def get_payment(self, payment_id: str) -> Optional[Dict]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # === LOGS ===
    def add_log(self, post_id: int, account_id: int, chat_id: int, status: str, error_msg: str = None):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO send_logs (post_id, account_id, chat_id, status, error_msg)
                   VALUES (?, ?, ?, ?, ?)""",
                (post_id, account_id, chat_id, status, error_msg)
            )


db = Database()
