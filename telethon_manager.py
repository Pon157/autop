"""Управление Telethon сессиями, флудвейтами, заморозками"""
import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserDeactivatedError, AuthKeyDuplicatedError, \
    SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty

import config
from database import db
from emoji_data import *


class AccountManager:
    def __init__(self):
        self.clients: Dict[int, TelegramClient] = {}
        self.flood_waits: Dict[int, int] = {}
        self._monitor_task = None
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)

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
        accounts = db.get_accounts()
        for acc in accounts:
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

    async def add_account(self, phone: str, code: str = None, password: str = None) -> Dict:
        os.makedirs(config.SESSIONS_DIR, exist_ok=True)
        session_name = f"session_{phone.replace('+', '').replace('-', '')}"
        session_path = os.path.join(config.SESSIONS_DIR, session_name)
        client = TelegramClient(session_path, config.API_ID, config.API_HASH)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                if not code:
                    await client.send_code_request(phone)
                    return {"status": "code_needed", "phone": phone, "session": session_name}
                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    if not password:
                        return {"status": "password_needed", "phone": phone, "session": session_name}
                    await client.sign_in(password=password)
                except (PhoneCodeInvalidError, PhoneCodeExpiredError):
                    return {"status": "error", "msg": "Неверный или просроченный код"}
            me = await client.get_me()
            db.add_account(phone, session_name)
            accounts = db.get_accounts()
            acc_id = None
            for a in accounts:
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

    async def get_account_dialogs(self, account_id: int) -> List[Dict]:
        if account_id not in self.clients:
            return []
        client = self.clients[account_id]
        try:
            dialogs = await client(GetDialogsRequest(
                offset_date=None, offset_id=0, offset_peer=InputPeerEmpty(),
                limit=200, hash=0
            ))
            result = []
            for dialog in dialogs.chats:
                chat_type = "channel" if hasattr(dialog, "broadcast") and dialog.broadcast else "chat"
                result.append({"id": dialog.id, "title": dialog.title, "type": chat_type})
            return result
        except Exception as e:
            print(f"[Dialogs Error] {e}")
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
            wait_time = e.seconds
            db.update_account_status(account_id, "flood_wait", wait_time)
            self.flood_waits[account_id] = int(datetime.now().timestamp()) + wait_time
            return {"status": "flood_wait", "wait": wait_time}
        except UserDeactivatedError:
            db.update_account_status(account_id, "banned")
            return {"status": "banned"}
        except Exception as e:
            return {"status": "error", "msg": str(e)}

    async def send_broadcast(self, post_id: int, account_id: int, chat_ids: List[int],
                            channel_id: int, channel_msg_id: int, interval: tuple = None):
        if account_id not in self.clients:
            return
        interval = interval or config.DEFAULT_SEND_INTERVAL
        for chat_id in chat_ids:
            post = db.get_post(post_id)
            if not post or post["status"] == "stopped":
                break
            if self.flood_waits.get(account_id, 0) > int(datetime.now().timestamp()):
                db.add_log(post_id, account_id, chat_id, "flood_wait",
                          f"Flood wait until {self.flood_waits[account_id]}")
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
        accounts = db.get_accounts()
        for acc in accounts:
            session_path = os.path.join(config.SESSIONS_DIR, acc["session_name"])
            if os.path.exists(f"{session_path}.session"):
                client = TelegramClient(session_path, config.API_ID, config.API_HASH)
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
