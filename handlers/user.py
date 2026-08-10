"""Панель пользователя — рассылка постов"""
import json
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from database import db
from telethon_manager import account_manager
from keyboards import *
from emoji_data import *

router = Router()

CHATS_PER_PAGE = 10


class UserStates(StatesGroup):
    waiting_post = State()
    creating_folder = State()
    editing_folder = State()


class BroadcastSetup(StatesGroup):
    selecting_accounts = State()
    selecting_folders = State()
    selecting_chats = State()
    confirm = State()


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


# === МОИ РАССЫЛКИ ===
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

    builder = InlineKeyboardBuilder()
    for post in posts[:5]:
        if post["status"] == "approved":
            builder.button(text=f"{GEAR} Настроить #{post['id']}", callback_data=f"post_setup_{post['id']}")
        elif post["status"] in ["sending", "stopped", "completed"]:
            builder.button(text=f"{CHART} Управление #{post['id']}", callback_data=f"post_manage_{post['id']}")

    builder.button(text=f"{BACK} Назад", callback_data="main_menu")
    builder.adjust(1)

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.answer(f"{CHART} Ваши рассылки")


@router.callback_query(F.data.startswith("post_manage_"))
async def cb_post_manage(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[-1])
    post = db.get_post(post_id)
    if not post:
        await callback.answer(f"{CROSS} Пост не найден", show_alert=True)
        return
    text = f"{CHART} <b>Управление рассылкой #{post_id}</b>" + "\n\n"
    text += f"{EYES} Статус: <b>{post['status']}</b>" + "\n"
    text += f"{GEAR} Аккаунты: {post['selected_accounts']}" + "\n"
    text += f"{FOLDER} Папки: {post['selected_folders']}" + "\n"
    text += f"{SPEECH} Чаты: {post['selected_chats']}"
    await callback.message.edit_text(text, reply_markup=post_control_kb(post_id, post["status"]), parse_mode="HTML")


# === НАСТРОЙКА РАССЫЛКИ ===
@router.callback_query(F.data.startswith("post_setup_"))
async def cb_post_setup(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split("_")[-1])
    post = db.get_post(post_id)
    if not post or post["user_id"] != callback.from_user.id:
        await callback.answer(f"{CROSS} Пост не найден", show_alert=True)
        return

    accounts = db.get_accounts(status="active")
    if not accounts:
        await callback.message.edit_text(f"{CROSS} Нет доступных аккаунтов для рассылки.", reply_markup=back_kb("menu_my_posts"))
        return

    await state.update_data(post_id=post_id, selected_accounts=[], selected_folders=[], selected_chats=[])
    await state.set_state(BroadcastSetup.selecting_accounts)

    text = f"{EYES} <b>Шаг 1/3: Выберите аккаунты</b>" + "\n\n"
    text += f"{INFO} Нажмите на аккаунт, чтобы выбрать/убрать."
    await callback.message.edit_text(text, reply_markup=_build_accounts_kb(post_id, accounts, []), parse_mode="HTML")


def _build_accounts_kb(post_id: int, accounts: list, selected: list):
    builder = InlineKeyboardBuilder()
    for acc in accounts:
        mark = CHECK if acc["id"] in selected else "⭕"
        builder.button(text=f"{mark} {acc['phone']}", callback_data=f"setup_acc_{post_id}_{acc['id']}")
    builder.button(text=f"{ARROW_RIGHT} Далее (выбрано {len(selected)})", callback_data=f"setup_acc_done_{post_id}")
    builder.button(text=f"{BACK} Назад", callback_data="menu_my_posts")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data.regexp(r"^setup_acc_\d+_\d+$"))
async def cb_setup_account(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    acc_id = int(parts[3])

    data = await state.get_data()
    selected = data.get("selected_accounts", [])

    if acc_id in selected:
        selected.remove(acc_id)
    else:
        selected.append(acc_id)

    await state.update_data(selected_accounts=selected)
    accounts = db.get_accounts(status="active")

    try:
        await callback.message.edit_reply_markup(reply_markup=_build_accounts_kb(post_id, accounts, selected))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("setup_acc_done_"))
async def cb_setup_acc_done(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    selected = data.get("selected_accounts", [])

    if not selected:
        await callback.answer(f"{WARNING} Выберите хотя бы один аккаунт!", show_alert=True)
        return

    db.update_post_accounts(post_id, selected)

    folders = db.get_folders(callback.from_user.id)
    if folders:
        await state.set_state(BroadcastSetup.selecting_folders)
        text = f"{FOLDER} <b>Шаг 2/3: Выберите папки</b>" + "\n\n"
        text += f"{INFO} Нажмите на папку, чтобы выбрать/убрать." + "\n"
        text += f"{INFO} Можно пропустить этот шаг."
        await callback.message.edit_text(text, reply_markup=_build_folders_kb(post_id, folders, []), parse_mode="HTML")
    else:
        await _go_to_chat_selection(callback, state, post_id)


def _build_folders_kb(post_id: int, folders: list, selected: list):
    builder = InlineKeyboardBuilder()
    for folder in folders:
        mark = CHECK if folder["id"] in selected else "⭕"
        builder.button(text=f"{mark} {folder['name']}", callback_data=f"setup_fold_{post_id}_{folder['id']}")
    builder.button(text=f"{ARROW_RIGHT} Далее", callback_data=f"setup_fold_done_{post_id}")
    builder.button(text=f"{SKIP} Пропустить", callback_data=f"setup_fold_skip_{post_id}")
    builder.button(text=f"{BACK} Назад", callback_data=f"post_setup_{post_id}")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data.regexp(r"^setup_fold_\d+_\d+$"))
async def cb_setup_folder(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    folder_id = int(parts[3])

    data = await state.get_data()
    selected = data.get("selected_folders", [])

    if folder_id in selected:
        selected.remove(folder_id)
    else:
        selected.append(folder_id)

    await state.update_data(selected_folders=selected)
    folders = db.get_folders(callback.from_user.id)

    try:
        await callback.message.edit_reply_markup(reply_markup=_build_folders_kb(post_id, folders, selected))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("setup_fold_done_"))
async def cb_setup_fold_done(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    selected = data.get("selected_folders", [])
    db.update_post_folders(post_id, selected)

    # Собираем чаты из папок
    chat_ids = []
    folders = db.get_folders(callback.from_user.id)
    for folder in folders:
        if folder["id"] in selected:
            chat_ids.extend(json.loads(folder["chat_ids"]))

    await state.update_data(selected_chats=chat_ids)
    await _go_to_chat_selection(callback, state, post_id)


@router.callback_query(F.data.startswith("setup_fold_skip_"))
async def cb_setup_fold_skip(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split("_")[-1])
    db.update_post_folders(post_id, [])
    await _go_to_chat_selection(callback, state, post_id)


async def _go_to_chat_selection(callback: CallbackQuery, state: FSMContext, post_id: int):
    data = await state.get_data()
    selected_accounts = data.get("selected_accounts", [])
    folder_chats = data.get("selected_chats", [])

    # Получаем диалоги со всех выбранных аккаунтов
    all_dialogs = []
    seen_ids = set()
    for acc_id in selected_accounts:
        dialogs = await account_manager.get_account_dialogs(acc_id)
        for d in dialogs:
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                all_dialogs.append(d)

    if not all_dialogs:
        # Fallback: ручной ввод
        await state.set_state(BroadcastSetup.selecting_chats)
        text = f"{SPEECH} <b>Шаг 3/3: Введите чаты</b>" + "\n\n"
        text += f"{INFO} Не удалось получить диалоги с аккаунтов." + "\n"
        text += f"{INFO} Введите ID чатов или @username через запятую:" + "\n"
        text += f"{EXAMPLE} Пример: <code>@channel1, @channel2, -1001234567890</code>"
        await callback.message.edit_text(text, reply_markup=back_kb("menu_my_posts"), parse_mode="HTML")
        return

    await state.update_data(available_chats=all_dialogs, selected_chats=folder_chats, chat_page=0)
    await state.set_state(BroadcastSetup.selecting_chats)

    text = f"{SPEECH} <b>Шаг 3/3: Выберите чаты</b>" + "\n\n"
    text += f"{INFO} Нажмите на чат, чтобы выбрать/убрать." + "\n"
    text += f"{INFO} Найдено чатов: <b>{len(all_dialogs)}</b>"
    if folder_chats:
        text += f"\n{CHECK} Уже выбрано из папок: <b>{len(folder_chats)}</b>"
    await callback.message.edit_text(text, reply_markup=_build_chats_kb(post_id, all_dialogs, folder_chats, 0), parse_mode="HTML")


def _build_chats_kb(post_id: int, chats: list, selected: list, page: int):
    builder = InlineKeyboardBuilder()
    start = page * CHATS_PER_PAGE
    end = start + CHATS_PER_PAGE
    page_chats = chats[start:end]

    for i, chat in enumerate(page_chats):
        idx = start + i
        mark = CHECK if chat["id"] in selected else "⭕"
        chat_type_emoji = {"channel": "📢", "group": "👥", "user": "👤"}.get(chat["type"], "💬")
        title = chat["title"][:28] if len(chat["title"]) <= 28 else chat["title"][:25] + "..."
        builder.button(text=f"{mark} {chat_type_emoji} {title}", callback_data=f"setup_chat_{post_id}_{idx}")

    # Навигация
    nav_row = []
    if page > 0:
        nav_row.append((f"{BACK} Назад", f"setup_chat_page_{post_id}_{page-1}"))
    if end < len(chats):
        nav_row.append((f"{ARROW_RIGHT} Вперёд", f"setup_chat_page_{post_id}_{page+1}"))
    for text, data in nav_row:
        builder.button(text=text, callback_data=data)

    builder.button(text=f"{CHECK} Готово ({len(selected)} чатов)", callback_data=f"setup_chat_done_{post_id}")
    builder.button(text=f"{BACK} Назад", callback_data=f"setup_fold_done_{post_id}")
    builder.adjust(1)
    return builder.as_markup()


@router.callback_query(F.data.regexp(r"^setup_chat_\d+_\d+$"))
async def cb_setup_chat(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    post_id = int(parts[2])
    idx = int(parts[3])

    data = await state.get_data()
    chats = data.get("available_chats", [])
    selected = data.get("selected_chats", [])
    page = data.get("chat_page", 0)

    if idx >= len(chats):
        await callback.answer("Ошибка")
        return

    chat_id = chats[idx]["id"]
    if chat_id in selected:
        selected.remove(chat_id)
    else:
        selected.append(chat_id)

    await state.update_data(selected_chats=selected)

    try:
        await callback.message.edit_reply_markup(reply_markup=_build_chats_kb(post_id, chats, selected, page))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.regexp(r"^setup_chat_page_\d+_\d+$"))
async def cb_setup_chat_page(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    post_id = int(parts[3])
    page = int(parts[4])

    data = await state.get_data()
    chats = data.get("available_chats", [])
    selected = data.get("selected_chats", [])

    await state.update_data(chat_page=page)

    try:
        await callback.message.edit_text(
            f"{SPEECH} <b>Шаг 3/3: Выберите чаты</b> (стр. {page+1})\n\n"
            f"{INFO} Нажмите на чат, чтобы выбрать/убрать.",
            reply_markup=_build_chats_kb(post_id, chats, selected, page),
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("setup_chat_done_"))
async def cb_setup_chat_done(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split("_")[-1])
    data = await state.get_data()
    selected = data.get("selected_chats", [])

    if not selected:
        await callback.answer(f"{WARNING} Выберите хотя бы один чат!", show_alert=True)
        return

    db.update_post_chats(post_id, selected)
    await state.set_state(BroadcastSetup.confirm)

    post = db.get_post(post_id)
    accounts = json.loads(post["selected_accounts"])
    chats_count = len(selected)

    text = f"{CHART} <b>Подтверждение рассылки #{post_id}</b>" + "\n\n"
    text += f"{EYES} Аккаунтов: <b>{len(accounts)}</b>" + "\n"
    text += f"{SPEECH} Чатов: <b>{chats_count}</b>" + "\n\n"
    text += f"{INFO} Запустить рассылку?"

    builder = InlineKeyboardBuilder()
    builder.button(text=f"{PLAY} Запустить", callback_data=f"post_start_{post_id}")
    builder.button(text=f"{BACK} Назад", callback_data="menu_my_posts")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# Fallback: ручной ввод чатов (если диалоги не получены)
@router.message(BroadcastSetup.selecting_chats)
async def process_chats_manual(message: Message, state: FSMContext):
    data = await state.get_data()
    post_id = data.get("post_id")
    existing_chats = data.get("selected_chats", [])

    raw = message.text.strip()
    new_chats = [c.strip() for c in raw.split(",") if c.strip()]

    all_chats = existing_chats + new_chats
    if not all_chats:
        await message.answer(f"{CROSS} Добавьте хотя бы один чат!", reply_markup=back_kb("menu_my_posts"))
        return

    db.update_post_chats(post_id, all_chats)
    await state.update_data(selected_chats=all_chats)
    await state.set_state(BroadcastSetup.confirm)

    post = db.get_post(post_id)
    accounts = json.loads(post["selected_accounts"])
    chats = json.loads(post["selected_chats"])

    text = f"{CHART} <b>Подтверждение рассылки #{post_id}</b>" + "\n\n"
    text += f"{EYES} Аккаунтов: <b>{len(accounts)}</b>" + "\n"
    text += f"{SPEECH} Чатов: <b>{len(chats)}</b>" + "\n\n"
    text += f"{INFO} Запустить рассылку?"

    builder = InlineKeyboardBuilder()
    builder.button(text=f"{PLAY} Запустить", callback_data=f"post_start_{post_id}")
    builder.button(text=f"{BACK} Назад", callback_data="menu_my_posts")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === УПРАВЛЕНИЕ РАССЫЛКОЙ ===
@router.callback_query(F.data.startswith("post_stop_"))
async def cb_post_stop(callback: CallbackQuery):
    post_id = int(callback.data.split("_")[-1])
    db.update_post_status(post_id, "stopped")
    await callback.answer(f"{PAUSE} Рассылка остановлена")
    await cb_post_manage(callback)


@router.callback_query(F.data.startswith("post_start_"))
async def cb_post_start(callback: CallbackQuery, state: FSMContext):
    post_id = int(callback.data.split("_")[-1])
    post = db.get_post(post_id)
    if not post:
        await callback.answer(f"{CROSS} Пост не найден", show_alert=True)
        return

    accounts_ids = json.loads(post["selected_accounts"]) if post["selected_accounts"] else []
    chat_ids = json.loads(post["selected_chats"]) if post["selected_chats"] else []

    if not accounts_ids or not chat_ids:
        await callback.answer(f"{CROSS} Сначала настройте аккаунты и чаты!", show_alert=True)
        return

    db.update_post_status(post_id, "sending")
    await callback.answer(f"{PLAY} Рассылка запущена")
    await state.clear()
    await start_broadcast(post_id, callback.bot)
    await cb_post_manage(callback)


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


# === ПАПКИ (с проверкой премиума на редактирование) ===
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


@router.callback_query(F.data.startswith("folder_edit_"))
async def cb_folder_edit(callback: CallbackQuery, state: FSMContext):
    # ПРОВЕРКА ПРЕМИУМА
    if not db.is_premium_active(callback.from_user.id):
        await callback.answer(f"{STOP} Редактирование папок доступно только в Премиум!", show_alert=True)
        return

    folder_id = int(callback.data.split("_")[-1])
    folders = db.get_folders(callback.from_user.id)
    folder = next((f for f in folders if f["id"] == folder_id), None)
    if not folder:
        await callback.answer(f"{CROSS} Папка не найдена", show_alert=True)
        return

    await state.update_data(edit_folder_id=folder_id)
    text = f"{PENCIL} <b>Редактирование папки '{folder['name']}'</b>" + "\n\n"
    text += f"{INFO} Отправьте ID чатов или @username через запятую:" + "\n"
    text += f"{EXAMPLE} Пример: <code>@channel1, @channel2, -1001234567890</code>" + "\n\n"
    current = json.loads(folder["chat_ids"])
    if current:
        text += f"{INFO} Текущие чаты: <code>{', '.join(map(str, current))}</code>"
    await callback.message.edit_text(text, reply_markup=back_kb(f"folder_view_{folder_id}"), parse_mode="HTML")
    await state.set_state(UserStates.editing_folder)


@router.message(UserStates.editing_folder)
async def process_edit_folder(message: Message, state: FSMContext):
    if not db.is_premium_active(message.from_user.id):
        await message.answer(f"{STOP} Только для Премиум!", reply_markup=main_menu_kb())
        await state.clear()
        return

    data = await state.get_data()
    folder_id = data.get("edit_folder_id")
    if not folder_id:
        await message.answer(f"{CROSS} Ошибка. Начните заново.")
        await state.clear()
        return

    raw = message.text.strip()
    chats = [c.strip() for c in raw.split(",") if c.strip()]
    db.update_folder_chats(folder_id, chats)

    text = f"{CHECK} Папка обновлена! Чатов: <b>{len(chats)}</b>"
    await message.answer(text, reply_markup=main_menu_kb(db.is_premium_active(message.from_user.id)), parse_mode="HTML")
    await state.clear()


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
