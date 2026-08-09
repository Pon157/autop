"""Панель пользователя — рассылка постов"""
import json
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import config
from database import db
from telethon_manager import account_manager
from keyboards import *
from emoji_data import *

router = Router()


class UserStates(StatesGroup):
    waiting_post = State()
    creating_folder = State()
    editing_folder = State()


@router.message(Command("start"))
async def cmd_start(message: Message):
    db.add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    is_premium = db.is_premium_active(message.from_user.id)
    is_owner = message.from_user.id in config.OWNER_IDS
    welcome_text = f"{STAR} <b>Добро пожаловать в авторассылку!</b>" + "\n\n"
    welcome_text += f"{SEND} Здесь вы можете разослать свои посты по чатам." + "\n"
    welcome_text += f"{INFO} Отправьте пост боту — он пройдет модерацию и будет разослан." + "\n\n"
    if is_premium:
        welcome_text += f"{DIAMOND} <b>Премиум активен!</b>" + "\n"
    else:
        welcome_text += f"{STAR} Купите Премиум для расширенных возможностей." + "\n"
    await message.answer(welcome_text, reply_markup=main_menu_kb(is_premium, is_owner), parse_mode="HTML")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    is_premium = db.is_premium_active(callback.from_user.id)
    is_owner = callback.from_user.id in config.OWNER_IDS
    await callback.message.edit_text(f"{STAR} <b>Главное меню</b>", reply_markup=main_menu_kb(is_premium, is_owner), parse_mode="HTML")


@router.callback_query(F.data == "menu_send_post")
async def cb_send_post(callback: CallbackQuery, state: FSMContext):
    text = f"{SEND} <b>Отправьте пост для рассылки</b>" + "\n\n"
    text += f"{INFO} Бот перешлет его в канал, откуда аккаунты разошлют по чатам." + "\n"
    text += f"{WARNING} Пост пройдет модерацию перед отправкой."
    await callback.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await state.set_state(UserStates.waiting_post)


@router.message(UserStates.waiting_post)
async def process_post(message: Message, state: FSMContext):
    try:
        forwarded = await message.forward(config.FORWARD_CHANNEL_ID)
        channel_msg_id = forwarded.message_id
    except Exception as e:
        await message.answer(f"{CROSS} Ошибка пересылки в канал: {e}", reply_markup=main_menu_kb())
        await state.clear()
        return
    post_id = db.create_pending_post(message.from_user.id, message.message_id)
    db.update_post_status(post_id, "pending", channel_msg_id)
    mod_text = f"{BELL} <b>Новый пост на модерацию!</b>" + "\n\n"
    mod_text += f"{EYES} От: <a href=\"tg://user?id={message.from_user.id}\">{message.from_user.first_name}</a>" + "\n"
    mod_text += f"{INFO} ID поста: <code>{post_id}</code>" + "\n\n"
    mod_text += f"{WARNING} Одобрить рассылку?"
    for owner_id in config.OWNER_IDS:
        try:
            await message.bot.send_message(owner_id, mod_text, reply_markup=moderation_kb(post_id), parse_mode="HTML")
        except Exception as e:
            print(f"[Moderation] Ошибка отправки owner {owner_id}: {e}")
    text = f"{CHECK} Пост отправлен на модерацию!" + "\n"
    text += f"{INFO} Вы получите уведомление после проверки."
    await message.answer(text, reply_markup=main_menu_kb(db.is_premium_active(message.from_user.id)), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "menu_my_posts")
async def cb_my_posts(callback: CallbackQuery):
    posts = db.get_user_posts(callback.from_user.id)
    if not posts:
        await callback.message.edit_text(f"{INFO} У вас пока нет рассылок.", reply_markup=back_kb())
        return
    text = f"{CHART} <b>Ваши рассылки:</b>" + "\n\n"
    for post in posts[:10]:
        status_emoji = {"pending": HOURGLASS, "approved": CHECK, "rejected": CROSS, "sending": PLAY, "completed": CHECK, "stopped": PAUSE}.get(post["status"], QUESTION)
        text += f"{status_emoji} Пост #{post['id']} — <b>{post['status']}</b>" + "\n"
    last_post = posts[0]
    await callback.message.edit_text(text, reply_markup=post_control_kb(last_post["id"], last_post["status"]), parse_mode="HTML")


@router.callback_query(F.data.startswith("post_stop_"))
async def cb_post_stop(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[-1])
    db.update_post_status(post_id, "stopped")
    await callback.answer(f"{PAUSE} Рассылка остановлена")
    await cb_my_posts(callback)


@router.callback_query(F.data.startswith("post_start_"))
async def cb_post_start(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[-1])
    db.update_post_status(post_id, "sending")
    await callback.answer(f"{PLAY} Рассылка запущена")
    await start_broadcast(post_id, callback.bot)
    await cb_my_posts(callback)


@router.callback_query(F.data.startswith("post_status_"))
async def cb_post_status(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[-1])
    post = db.get_post(post_id)
    if not post:
        await callback.answer(f"{CROSS} Пост не найден", show_alert=True)
        return
    text = f"{CHART} <b>Статус рассылки #{post_id}</b>" + "\n\n"
    text += f"{EYES} Статус: <b>{post['status']}</b>" + "\n"
    text += f"{GEAR} Аккаунты: {post['selected_accounts']}" + "\n"
    text += f"{FOLDER} Папки: {post['selected_folders']}" + "\n"
    text += f"{SPEECH} Чаты: {post['selected_chats']}"
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("post_delete_"))
async def cb_post_delete(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[-1])
    db.update_post_status(post_id, "rejected")
    await callback.answer(f"{TRASH} Рассылка удалена")
    await cb_my_posts(callback)


async def start_broadcast_setup(callback: CallbackQuery, post_id: int):
    accounts = db.get_accounts(status="active")
    if not accounts:
        await callback.message.edit_text(f"{CROSS} Нет доступных аккаунтов для рассылки.", reply_markup=back_kb())
        return
    await callback.message.edit_text(f"{EYES} <b>Выберите аккаунты для рассылки:</b>", reply_markup=select_accounts_kb(accounts), parse_mode="HTML")


@router.callback_query(F.data == "menu_folders")
async def cb_folders(callback: CallbackQuery):
    folders = db.get_folders(callback.from_user.id)
    text = f"{FOLDER} <b>Ваши папки</b>" + "\n\n"
    text += f"{INFO} Управляйте группами чатов для рассылки."
    await callback.message.edit_text(text, reply_markup=folder_list_kb(folders), parse_mode="HTML")


@router.callback_query(F.data == "folder_create")
async def cb_folder_create(callback: CallbackQuery, state: FSMContext):
    text = f"{PLUS} <b>Создание папки</b>" + "\n\n"
    text += f"{INFO} Введите название папки:"
    await callback.message.edit_text(text, reply_markup=back_kb("menu_folders"), parse_mode="HTML")
    await state.set_state(UserStates.creating_folder)


@router.message(UserStates.creating_folder)
async def process_folder_name(message: Message, state: FSMContext):
    name = message.text.strip()
    db.add_folder(message.from_user.id, name, "[]")
    text = f"{CHECK} Папка <b>\"{name}\"</b> создана!" + "\n"
    text += f"{INFO} Теперь добавьте чаты через панель."
    await message.answer(text, reply_markup=main_menu_kb(db.is_premium_active(message.from_user.id)), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data.startswith("folder_view_"))
async def cb_folder_view(callback: CallbackQuery):
    folder_id = int(callback.data.split("_")[-1])
    folders = db.get_folders(callback.from_user.id)
    folder = next((f for f in folders if f["id"] == folder_id), None)
    if not folder:
        await callback.answer(f"{CROSS} Папка не найдена", show_alert=True)
        return
    chats = json.loads(folder["chat_ids"])
    text = f"{FOLDER} <b>{folder['name']}</b>" + "\n\n"
    text += f"{INFO} Чатов: <b>{len(chats)}</b>" + "\n"
    for chat in chats[:10]:
        text += f"   • {chat}" + "\n"
    await callback.message.edit_text(text, reply_markup=folder_detail_kb(folder_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("folder_delete_"))
async def cb_folder_delete(callback: CallbackQuery):
    folder_id = int(callback.data.split("_")[-1])
    db.delete_folder(folder_id)
    await callback.answer(f"{TRASH} Папка удалена")
    await cb_folders(callback)


@router.callback_query(F.data == "menu_help")
async def cb_help(callback: CallbackQuery):
    text = f"{INFO} <b>Помощь</b>" + "\n\n"
    text += f"{SEND} <b>Как разослать пост?</b>" + "\n"
    text += f"1. Нажмите {SEND} Разослать пост" + "\n"
    text += f"2. Отправьте пост боту" + "\n"
    text += f"3. Дождитесь модерации" + "\n"
    text += f"4. Выберите аккаунты и чаты" + "\n"
    text += f"5. Запустите рассылку" + "\n\n"
    text += f"{DIAMOND} <b>Премиум</b> дает:" + "\n"
    text += f"• Выделенный аккаунт" + "\n"
    text += f"• Нет очереди" + "\n"
    text += f"• Настройка интервалов (до 20 сек)" + "\n"
    text += f"• Собственные папки чатов" + "\n\n"
    text += f"{WARNING} Все рассылки проходят модерацию."
    await callback.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")


async def start_broadcast(post_id: int, bot):
    post = db.get_post(post_id)
    if not post or post["status"] != "sending":
        return
    accounts_ids = json.loads(post["selected_accounts"]) if post["selected_accounts"] else []
    chat_ids = json.loads(post["selected_chats"]) if post["selected_chats"] else []
    if not accounts_ids or not chat_ids:
        db.update_post_status(post_id, "stopped")
        return
    channel_id = config.FORWARD_CHANNEL_ID
    channel_msg_id = post["channel_message_id"]
    chats_per_account = len(chat_ids) // len(accounts_ids) or 1
    for i, acc_id in enumerate(accounts_ids):
        start_idx = i * chats_per_account
        end_idx = start_idx + chats_per_account if i < len(accounts_ids) - 1 else len(chat_ids)
        acc_chats = chat_ids[start_idx:end_idx]
        asyncio.create_task(account_manager.send_broadcast(post_id, acc_id, acc_chats, channel_id, channel_msg_id))
    asyncio.create_task(_check_broadcast_complete(post_id))


async def _check_broadcast_complete(post_id: int):
    await asyncio.sleep(60)
    post = db.get_post(post_id)
    if post and post["status"] == "sending":
        db.update_post_status(post_id, "completed")
