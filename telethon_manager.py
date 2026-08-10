"""Управление Telethon сессиями"""
import os
import asyncio
from datetime import datetime
from typing import List, Dict
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserDeactivatedError, \
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty

import config
from database import db
from emoji_data import *


def _get_proxy():
    return config.parse_proxy(config.PROXY_URL)


class AccountManager:
    def __init__(self):
        self.clients: Dict[int, TelegramClient] = {}
        self.flood_waits: Dict[int, int] = {}
        self._code_hashes: Dict[str, str] = {}
        self._pending_qr: Dict[str, dict] = {}
        self._pending_auth: Dict[str, dict] = {}
        self._monitor_task = None
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)

    def _get_api(self, account_id: int = None):
        """API для аккаунта (из БД) или глобальные (из .env)."""
        if account_id:
            acc = db.get_account(account_id)
            if acc and acc.get("api_id") and acc.get("api_hash"):
                return int(acc["api_id"]), acc["api_hash"]
        api_id = int(os.getenv("API_ID", "0")) if os.getenv("API_ID") else 0
        api_hash = os.getenv("API_HASH", "")
        return api_id, api_hash

    async def start_monitoring(self):
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        while True:
            try:
                await self._check_accounts()
            except Exception as e:
                print(f"[Monitor Error] {e}")
            await asyncio.sleep(30)

    async def _check_accounts(self):
        for acc in db.get_accounts():
            acc_id = acc["id"]
            if acc["flood_wait_until"] > int(datetime.now().timestamp()):
                if acc["status"] != "flood_wait":
                    db.update_account_status(acc_id, "flood_wait")
                continue
            if acc_id in self.clients:
                client = self.clients[acc_id]
                if not client.is_connected():
                    try:
                        await client.connect()
                        if acc["status"] == "error":
                            db.update_account_status(acc_id, "active")
                    except Exception as e:
                        db.update_account_status(acc_id, "error")
                        print(f"[Account {acc_id}] Connection error: {e}")

    async def add_account(self, phone: str, code: str = None, password: str = None, api_id: str = None, api_hash: str = None) -> Dict:
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)
        aid = int(api_id) if api_id else 0
        ahash = api_hash or ""
        if not aid or not ahash:
            return {"status": "error", "msg": "Укажите API_ID и API_HASH для этого аккаунта."}

        session_name = f"session_{phone.replace('+', '').replace('-', '')}"
        session_path = os.path.join(config.SESSIONS_DIR, session_name)
        proxy = _get_proxy()
        client = TelegramClient(session_path, aid, ahash, proxy=proxy)

        try:
            await client.connect()
            if not await client.is_user_authorized():
                if not code:
                    result = await client.send_code_request(phone)
                    self._code_hashes[phone] = result.phone_code_hash
                    return {"status": "code_needed", "phone": phone, "session": session_name, "api_id": aid, "api_hash": ahash}
                pch = self._code_hashes.get(phone)
                if not pch:
                    return {"status": "error", "msg": "Сессия устарела. Начните заново."}
                try:
                    await client.sign_in(phone, code, phone_code_hash=pch)
                except SessionPasswordNeededError:
                    if not password:
                        self._pending_auth[phone] = {
                            "client": client,
                            "session_name": session_name,
                            "api_id": str(aid),
                            "api_hash": ahash
                        }
                        return {
                            "status": "password_needed",
                            "phone": phone,
                            "session": session_name,
                            "api_id": aid,
                            "api_hash": ahash
                        }
                    await client.sign_in(password=password)
                except (PhoneCodeInvalidError, PhoneCodeExpiredError):
                    return {"status": "error", "msg": "Неверный или просроченный код"}
            me = await client.get_me()
            db.add_account(phone, session_name, str(aid), ahash)
            acc_id = None
            for a in db.get_accounts():
                if a["phone"] == phone:
                    acc_id = a["id"]
                    break
            if acc_id:
                self.clients[acc_id] = client
            else:
                await client.disconnect()
            return {"status": "success", "phone": phone, "name": me.first_name, "id": acc_id}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "msg": str(e)}

    async def complete_password_login(self, phone: str, password: str) -> Dict:
        """Завершает вход по коду, когда требуется 2FA-пароль."""
        pending = self._pending_auth.get(phone)
        if not pending:
            return {"status": "error", "msg": "Сессия устарела. Начните заново."}

        client = pending["client"]
        session_name = pending["session_name"]
        api_id = pending["api_id"]
        api_hash = pending["api_hash"]

        try:
            await client.sign_in(password=password)
            me = await client.get_me()
            db.add_account(phone, session_name, api_id, api_hash)
            acc_id = None
            for a in db.get_accounts():
                if a["phone"] == phone:
                    acc_id = a["id"]
                    break
            if acc_id:
                self.clients[acc_id] = client
            else:
                await client.disconnect()
            return {"status": "success", "phone": phone, "name": me.first_name, "id": acc_id}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "msg": str(e)}
        finally:
            self._pending_auth.pop(phone, None)

    async def start_qr_login(self, phone: str, owner_id: int, bot, api_id: str = None, api_hash: str = None) -> dict:
        try:
            import qrcode
            from io import BytesIO
            QR_AVAILABLE = True
        except ImportError:
            QR_AVAILABLE = False

        aid = int(api_id) if api_id else 0
        ahash = api_hash or ""
        if not aid or not ahash:
            return {"status": "error", "msg": "Укажите API_ID и API_HASH для этого аккаунта."}

        os.makedirs(config.SESSIONS_DIR, exist_ok=True)
        session_name = f"session_{phone.replace('+', '').replace('-', '')}"
        session_path = os.path.join(config.SESSIONS_DIR, session_name)
        proxy = _get_proxy()
        client = TelegramClient(session_path, aid, ahash, proxy=proxy)

        try:
            await client.connect()
            if await client.is_user_authorized():
                me = await client.get_me()
                db.add_account(phone, session_name, str(aid), ahash)
                acc_id = None
                for a in db.get_accounts():
                    if a["phone"] == phone:
                        acc_id = a["id"]
                        break
                if acc_id:
                    self.clients[acc_id] = client
                return {"status": "success", "phone": phone, "name": me.first_name, "id": acc_id}

            qr_login = await client.qr_login()
            self._pending_qr[phone] = {
                "client": client, "qr_login": qr_login, "session": session_name,
                "owner_id": owner_id, "bot": bot, "api_id": str(aid), "api_hash": ahash,
                "needs_password": False
            }

            if QR_AVAILABLE:
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(qr_login.url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format='PNG')
                buffer.seek(0)
                return {"status": "qr_image", "phone": phone, "qr_buffer": buffer, "qr_url": qr_login.url}
            else:
                return {"status": "qr_url", "phone": phone, "qr_url": qr_login.url}
        except Exception as e:
            await client.disconnect()
            return {"status": "error", "msg": str(e)}

    async def wait_qr_login(self, phone: str, password: str = None):
        pending = self._pending_qr.get(phone)
        if not pending:
            return
        client = pending["client"]
        qr_login = pending["qr_login"]
        owner_id = pending["owner_id"]
        bot = pending["bot"]
        session_name = pending["session"]
        api_id = pending["api_id"]
        api_hash = pending["api_hash"]

        try:
            await qr_login.wait(timeout=180)
        except SessionPasswordNeededError:
            if not password:
                pending["needs_password"] = True
                await bot.send_message(
                    owner_id,
                    f"{LOCK} <b>Требуется пароль 2FA</b>\n\n"
                    f"{INFO} Введите пароль от аккаунта {phone}:\n"
                    f"{WARNING} Отправьте /password ваш_пароль",
                    parse_mode="HTML"
                )
                return
            try:
                await client.sign_in(password=password)
            except Exception as e:
                await client.disconnect()
                await bot.send_message(owner_id, f"{CROSS} Ошибка 2FA: {str(e)[:200]}", parse_mode="HTML")
                del self._pending_qr[phone]
                return
        except asyncio.TimeoutError:
            await client.disconnect()
            await bot.send_message(owner_id, f"{CROSS} Время ожидания QR истекло (3 мин).", parse_mode="HTML")
            del self._pending_qr[phone]
            return
        except Exception as e:
            await client.disconnect()
            await bot.send_message(owner_id, f"{CROSS} Ошибка QR: {str(e)[:200]}", parse_mode="HTML")
            del self._pending_qr[phone]
            return

        try:
            me = await client.get_me()
            db.add_account(phone, session_name, api_id, api_hash)
            acc_id = None
            for a in db.get_accounts():
                if a["phone"] == phone:
                    acc_id = a["id"]
                    break
            if acc_id:
                self.clients[acc_id] = client
            await bot.send_message(
                owner_id,
                f"{CHECK} Аккаунт <b>{me.first_name}</b> ({phone}) добавлен через QR!\n{EYES} ID: {acc_id}",
                parse_mode="HTML"
            )
        except Exception as e:
            await client.disconnect()
            await bot.send_message(owner_id, f"{CROSS} Ошибка: {str(e)[:200]}", parse_mode="HTML")
        finally:
            if phone in self._pending_qr:
                del self._pending_qr[phone]

    async def complete_qr_password_login(self, phone: str, password: str) -> Dict:
        """Завершает QR-вход, когда требуется 2FA-пароль."""
        pending = self._pending_qr.get(phone)
        if not pending:
            return {"status": "error", "msg": "Сессия устарела. Начните заново."}
        if not pending.get("needs_password"):
            return {"status": "error", "msg": "Пароль не требуется или уже обработан."}

        client = pending["client"]
        owner_id = pending["owner_id"]
        bot = pending["bot"]
        session_name = pending["session"]
        api_id = pending["api_id"]
        api_hash = pending["api_hash"]

        try:
            await client.sign_in(password=password)
            me = await client.get_me()
            db.add_account(phone, session_name, api_id, api_hash)
            acc_id = None
            for a in db.get_accounts():
                if a["phone"] == phone:
                    acc_id = a["id"]
                    break
            if acc_id:
                self.clients[acc_id] = client
            await bot.send_message(
                owner_id,
                f"{CHECK} Аккаунт <b>{me.first_name}</b> ({phone}) добавлен через QR!\n{EYES} ID: {acc_id}",
                parse_mode="HTML"
            )
            return {"status": "success", "phone": phone, "name": me.first_name, "id": acc_id}
        except Exception as e:
            await client.disconnect()
            await bot.send_message(owner_id, f"{CROSS} Ошибка 2FA: {str(e)[:200]}", parse_mode="HTML")
            return {"status": "error", "msg": str(e)}
        finally:
            self._pending_qr.pop(phone, None)

    async def import_session_file(self, phone: str, session_bytes: bytes, owner_id: int, bot, api_id: str = None, api_hash: str = None) -> dict:
        aid = int(api_id) if api_id else 0
        ahash = api_hash or ""
        if not aid or not ahash:
            return {"status": "error", "msg": "Укажите API_ID и API_HASH для этого аккаунта."}

        os.makedirs(config.SESSIONS_DIR, exist_ok=True)
        session_name = f"session_{phone.replace('+', '').replace('-', '')}"
        session_path = os.path.join(config.SESSIONS_DIR, session_name)
        try:
            with open(f"{session_path}.session", "wb") as f:
                f.write(session_bytes)
            proxy = _get_proxy()
            client = TelegramClient(session_path, aid, ahash, proxy=proxy)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                os.remove(f"{session_path}.session")
                return {"status": "error", "msg": "Сессия не авторизована."}
            me = await client.get_me()
            db.add_account(phone, session_name, str(aid), ahash)
            acc_id = None
            for a in db.get_accounts():
                if a["phone"] == phone:
                    acc_id = a["id"]
                    break
            if acc_id:
                self.clients[acc_id] = client
            else:
                await client.disconnect()
            return {"status": "success", "phone": phone, "name": me.first_name, "id": acc_id}
        except Exception as e:
            if os.path.exists(f"{session_path}.session"):
                os.remove(f"{session_path}.session")
            return {"status": "error", "msg": str(e)}

    async def get_account_dialogs(self, account_id: int) -> List[Dict]:
        """Получает диалоги аккаунта через iter_dialogs."""
        if account_id not in self.clients:
            return []
        client = self.clients[account_id]
        try:
            dialogs = []
            async for dialog in client.iter_dialogs(limit=200):
                title = dialog.title or dialog.name or str(dialog.id)
                if dialog.is_channel:
                    chat_type = "channel"
                elif dialog.is_group:
                    chat_type = "group"
                else:
                    chat_type = "user"
                dialogs.append({
                    "id": dialog.id,
                    "title": title,
                    "type": chat_type
                })
            return dialogs
        except Exception as e:
            print(f"[Dialogs Error] Account {account_id}: {e}")
            return []

    async def forward_post(self, account_id: int, from_chat: int, message_id: int, to_chat: int) -> Dict:
        if account_id not in self.clients:
            return {"status": "error", "msg": "Аккаунт не подключен"}
        client = self.clients[account_id]
        try:
            await client.forward_messages(to_chat, message_id, from_chat)
            db.increment_account_load(account_id)
            return {"status": "success"}
        except FloodWaitError as e:
            db.update_account_status(account_id, "flood_wait", e.seconds)
            self.flood_waits[account_id] = int(datetime.now().timestamp()) + e.seconds
            return {"status": "flood_wait", "wait": e.seconds}
        except UserDeactivatedError:
            db.update_account_status(account_id, "banned")
            return {"status": "banned"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    async def send_broadcast(self, post_id: int, account_id: int, chat_ids: List[int], channel_id: int, channel_msg_id: int, interval: tuple = None):
        if account_id not in self.clients:
            return
        interval = interval or config.DEFAULT_SEND_INTERVAL
        for chat_id in chat_ids:
            post = db.get_post(post_id)
            if not post or post["status"] == "stopped":
                break
            if self.flood_waits.get(account_id, 0) > int(datetime.now().timestamp()):
                db.add_log(post_id, account_id, chat_id, "flood_wait", f"Flood wait until {self.flood_waits[account_id]}")
                continue
            result = await self.forward_post(account_id, channel_id, channel_msg_id, chat_id)
            if result["status"] == "success":
                db.add_log(post_id, account_id, chat_id, "success")
            else:
                db.add_log(post_id, account_id, chat_id, result["status"], result.get("msg"))
                if result["status"] in ["banned", "flood_wait"]:
                    break
            delay = interval[0] if len(interval) == 1 else __import__("random").randint(interval[0], interval[1])
            await asyncio.sleep(delay)

    async def load_sessions(self):
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)
        for acc in db.get_accounts():
            aid = int(acc["api_id"]) if acc.get("api_id") else 0
            ahash = acc.get("api_hash", "")
            if not aid or not ahash:
                continue
            session_path = os.path.join(config.SESSIONS_DIR, acc["session_name"])
            if os.path.exists(f"{session_path}.session"):
                proxy = _get_proxy()
                client = TelegramClient(session_path, aid, ahash, proxy=proxy)
                try:
                    await client.connect()
                    if await client.is_user_authorized():
                        self.clients[acc["id"]] = client
                        if acc["status"] in ["error", "banned"]:
                            try:
                                await client.get_me()
                                db.update_account_status(acc["id"], "active")
                            except UserDeactivatedError:
                                db.update_account_status(acc["id"], "banned")
                    else:
                        await client.disconnect()
                except Exception as e:
                    print(f"[Load Session] Error for {acc['phone']}: {e}")
                    await client.disconnect()

    async def disconnect_all(self):
        for client in self.clients.values():
            await client.disconnect()
        self.clients.clear()


account_manager = AccountManager()
