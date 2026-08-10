"""Панель администратора (owner)"""
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
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
NL = chr(10)


class AdminStates(StatesGroup):
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()
    waiting_phone_qr = State()
    waiting_phone_session = State()
    waiting_session_file = State()


def is_owner(user_id: int) -> bool:
    return user_id in config.OWNER_IDS


# === ГЛАВНЫЕ ОБРАБОТЧИКИ ===
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer(f"{STOP} Доступ запрещен.")
        return
    await show_admin_panel(message.answer, message.from_user.id)


@router.callback_query(F.data == "menu_admin")
async def cb_menu_admin(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer(f"{STOP} Нет доступа!", show_alert=True)
        return
    await show_admin_panel(callback.message.edit_text, callback.from_user.id)


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel_alias(callback: CallbackQuery):
    """Alias для кнопок 'Назад' которые используют admin_panel"""
    await cb_menu_admin(callback)


async def show_admin_panel(send_fn, user_id: int):
    text = f"{GEAR} <b>Админ панель</b>" + NL + NL + f"{EYES} Управление аккаунтами и статистикой."
    await send_fn(text, reply_markup=admin_panel_kb(), parse_mode="HTML")


# === API НАСТРОЙКИ ===
@router.callback_query(F.data == "admin_api_settings")
async def cb_api_settings(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    api_id, api_hash = db.get_api_credentials()
    source = "из БД" if db.get_setting("api_id") else "из .env (fallback)"
    text = f"{GEAR} <b>API настройки</b>" + NL + NL
    text += f"{INFO} Источник: <b>{source}</b>" + NL
    text += f"{EYES} API_ID: <code>{api_id or 'не задан'}</code>" + NL
    text += f"{EYES} API_HASH: <code>{api_hash[:8] + '...' if api_hash else 'не задан'}</code>" + NL + NL
    text += f"{WARNING} Эти данные нужны для работы Telethon. Получите на my.telegram.org"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{PENCIL} Изменить API_ID", callback_data="set_api_id")
    builder.button(text=f"{PENCIL} Изменить API_HASH", callback_data="set_api_hash")
    builder.button(text=f"{BACK} Назад", callback_data="admin_panel")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "set_api_id")
async def cb_set_api_id(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        return
    text = f"{PENCIL} <b>Введите API_ID</b>" + NL + NL
    text += f"{INFO} Получите на <a href=\"https://my.telegram.org/apps\">my.telegram.org</a>" + NL
    text += f"{WARNING} Только цифры, например: <code>123456</code>"
    await callback.message.edit_text(text, reply_markup=back_kb("admin_api_settings"), parse_mode="HTML", disable_web_page_preview=True)
    await state.set_state(AdminStates.waiting_api_id)


@router.message(AdminStates.waiting_api_id)
async def process_api_id(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    val = message.text.strip()
    if not val.isdigit():
        await message.answer(f"{CROSS} API_ID должен содержать только цифры.", reply_markup=back_kb("admin_api_settings"))
        return
    db.set_setting("api_id", val)
    text = f"{CHECK} API_ID сохранен: <code>{val}</code>" + NL + NL
    api_hash = db.get_setting("api_hash")
    if not api_hash:
        text += f"{WARNING} Теперь введите API_HASH через админ-панель."
    else:
        text += f"{INFO} API_HASH уже задан. Можно добавлять аккаунты."
    await message.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "set_api_hash")
async def cb_set_api_hash(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        return
    text = f"{PENCIL} <b>Введите API_HASH</b>" + NL + NL
    text += f"{INFO} Получите на <a href=\"https://my.telegram.org/apps\">my.telegram.org</a>" + NL
    text += f"{WARNING} Строка из букв и цифр, например: <code>a1b2c3d4e5f6...</code>"
    await callback.message.edit_text(text, reply_markup=back_kb("admin_api_settings"), parse_mode="HTML", disable_web_page_preview=True)
    await state.set_state(AdminStates.waiting_api_hash)


@router.message(AdminStates.waiting_api_hash)
async def process_api_hash(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    val = message.text.strip()
    if len(val) < 10:
        await message.answer(f"{CROSS} API_HASH слишком короткий.", reply_markup=back_kb("admin_api_settings"))
        return
    db.set_setting("api_hash", val)
    text = f"{CHECK} API_HASH сохранен." + NL + NL
    api_id = db.get_setting("api_id")
    if not api_id:
        text += f"{WARNING} Теперь введите API_ID через админ-панель."
    else:
        text += f"{INFO} API_ID уже задан. Можно добавлять аккаунты."
    await message.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
    await state.clear()


# === ДОБАВЛЕНИЕ АККАУНТА — СНАЧАЛА API ===
@router.callback_query(F.data == "admin_add_account")
async def cb_add_account(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        return
    text = f"{PLUS} <b>Добавление аккаунта</b>" + NL + NL
    text += f"{INFO} Сначала введите API_ID и API_HASH для этого аккаунта." + NL
    text += f"{WARNING} Каждый аккаунт должен иметь <b>свои</b> API credentials — так Telegram не банит." + NL + NL
    text += f"{INFO} Введите API_ID (только цифры):"
    await callback.message.edit_text(text, reply_markup=back_kb("admin_panel"), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_api_id)
    await state.update_data(add_account_flow=True)


@router.message(AdminStates.waiting_api_id)
async def process_add_api_id(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    data = await state.get_data()
    if not data.get("add_account_flow"):
        # Это обычный ввод API_ID из настроек — делегируем
        await process_api_id(message, state)
        return
    val = message.text.strip()
    if not val.isdigit():
        await message.answer(f"{CROSS} API_ID только цифры.", reply_markup=back_kb("admin_panel"))
        return
    await state.update_data(api_id=val)
    text = f"{CHECK} API_ID: <code>{val}</code>" + NL + NL
    text += f"{INFO} Теперь введите API_HASH:"
    await message.answer(text, reply_markup=back_kb("admin_panel"), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_api_hash)


@router.message(AdminStates.waiting_api_hash)
async def process_add_api_hash(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    data = await state.get_data()
    if not data.get("add_account_flow"):
        await process_api_hash(message, state)
        return
    val = message.text.strip()
    if len(val) < 10:
        await message.answer(f"{CROSS} API_HASH слишком короткий.", reply_markup=back_kb("admin_panel"))
        return
    await state.update_data(api_hash=val)
    text = f"{CHECK} API сохранены для нового аккаунта." + NL + NL
    text += f"{INFO} Выберите способ входа:"
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{CHECK} По коду", callback_data="add_method_code")
    builder.button(text=f"{QR} По QR-коду", callback_data="add_method_qr")
    builder.button(text=f"{UPLOAD} .session файл", callback_data="add_method_session")
    builder.button(text=f"{BACK} Назад", callback_data="admin_panel")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


# === СПОСОБЫ ВХОДА ===
@router.callback_query(F.data == "add_method_code")
async def cb_method_code(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        return
    text = f"{CHECK} <b>Вход по коду</b>" + NL + NL
    text += f"{WARNING} <b>Внимание:</b> если бот и ваш Telegram на одном сервере/IP, вход заблокирует Telegram!" + NL + NL
    text += f"{INFO} Введите номер телефона в формате +79991234567:"
    await callback.message.edit_text(text, reply_markup=back_kb("admin_panel"), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_phone)


@router.message(AdminStates.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    result = await account_manager.add_account(phone, api_id=data.get("api_id"), api_hash=data.get("api_hash"))
    if result["status"] == "code_needed":
        text = f"{BELL} Код отправлен на {phone}." + NL + f"{INFO} Введите код из Telegram:"
        await message.answer(text, reply_markup=back_kb("admin_panel"))
        await state.set_state(AdminStates.waiting_code)
    elif result["status"] == "success":
        text = f"{CHECK} Аккаунт <b>{result['name']}</b> ({phone}) добавлен!" + NL + f"{EYES} ID: {result['id']}"
        await message.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
        await state.clear()
    else:
        text = f"{CROSS} Ошибка: {result.get('msg', 'Неизвестная ошибка')}"
        await message.answer(text, reply_markup=admin_panel_kb())
        await state.clear()


@router.message(AdminStates.waiting_code)
async def process_code(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    data = await state.get_data()
    phone = data["phone"]
    code = message.text.strip()
    result = await account_manager.add_account(phone, code=code, api_id=data.get("api_id"), api_hash=data.get("api_hash"))
    if result["status"] == "password_needed":
        text = f"{LOCK} Требуется пароль 2FA." + NL + f"{INFO} Введите пароль:"
        await message.answer(text, reply_markup=back_kb("admin_panel"))
        await state.set_state(AdminStates.waiting_password)
    elif result["status"] == "success":
        text = f"{CHECK} Аккаунт <b>{result['name']}</b> добавлен!" + NL + f"{EYES} ID: {result['id']}"
        await message.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
        await state.clear()
    else:
        text = f"{CROSS} Ошибка: {result.get('msg', 'Неизвестная ошибка')}"
        await message.answer(text, reply_markup=admin_panel_kb())
        await state.clear()


@router.message(AdminStates.waiting_password)
async def process_password(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    data = await state.get_data()
    phone = data["phone"]
    code = data.get("code", "")
    password = message.text.strip()
    result = await account_manager.add_account(phone, code=code, password=password, api_id=data.get("api_id"), api_hash=data.get("api_hash"))
    if result["status"] == "success":
        text = f"{CHECK} Аккаунт <b>{result['name']}</b> добавлен!" + NL + f"{EYES} ID: {result['id']}"
        await message.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
    else:
        text = f"{CROSS} Ошибка: {result.get('msg', 'Неизвестная ошибка')}"
        await message.answer(text, reply_markup=admin_panel_kb())
    await state.clear()


@router.callback_query(F.data == "add_method_qr")
async def cb_method_qr(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        return
    text = f"{QR} <b>Вход по QR-коду</b>" + NL + NL
    text += f"{INFO} Введите номер телефона в формате +79991234567:"
    await callback.message.edit_text(text, reply_markup=back_kb("admin_panel"), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_phone_qr)


@router.message(AdminStates.waiting_phone_qr)
async def process_phone_qr(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()
    result = await account_manager.start_qr_login(phone, message.from_user.id, message.bot, api_id=data.get("api_id"), api_hash=data.get("api_hash"))
    if result["status"] == "success":
        text = f"{CHECK} Аккаунт <b>{result['name']}</b> ({phone}) уже авторизован!" + NL + f"{EYES} ID: {result['id']}"
        await message.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
        await state.clear()
    elif result["status"] == "qr_image":
        buffer = result["qr_buffer"]
        caption = f"{QR} <b>Отсканируйте QR-код</b>" + NL + NL
        caption += f"{INFO} Откройте Telegram -> Настройки -> Устройства -> Подключить устройство" + NL
        caption += f"{WARNING} У вас есть 3 минуты!" + NL + NL
        caption += f"{LINK} Или ссылка: {result['qr_url']}"
        await message.answer_photo(BufferedInputFile(buffer.read(), filename="qr.png"), caption=caption, parse_mode="HTML")
        asyncio.create_task(account_manager.wait_qr_login(phone))
        await state.clear()
    elif result["status"] == "qr_url":
        text = f"{QR} <b>Подключение по QR</b>" + NL + NL
        text += f"{LINK} <a href=\"{result['qr_url']}\">Нажмите здесь</a>" + NL + NL
        text += f"{WARNING} У вас есть 3 минуты!"
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
        asyncio.create_task(account_manager.wait_qr_login(phone))
        await state.clear()
    else:
        text = f"{CROSS} Ошибка: {result.get('msg', 'Неизвестная ошибка')}"
        await message.answer(text, reply_markup=admin_panel_kb())
        await state.clear()


@router.callback_query(F.data == "add_method_session")
async def cb_method_session(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        return
    text = f"{UPLOAD} <b>Загрузка .session</b>" + NL + NL
    text += f"{INFO} 1. Авторизуйтесь через Telethon на другом устройстве" + NL
    text += f"{INFO} 2. Найдите файл <code>session_xxx.session</code>" + NL
    text += f"{INFO} 3. Введите номер телефона, затем отправьте файл"
    await callback.message.edit_text(text, reply_markup=back_kb("admin_panel"), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_phone_session)


@router.message(AdminStates.waiting_phone_session)
async def process_phone_session(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    phone = message.text.strip()
    await state.update_data(phone=phone)
    text = f"{UPLOAD} Отправьте <b>.session</b> файл для {phone}"
    await message.answer(text, reply_markup=back_kb("admin_panel"), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_session_file)


@router.message(AdminStates.waiting_session_file)
async def process_session_file(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    if not message.document or not message.document.file_name.endswith('.session'):
        await message.answer(f"{CROSS} Отправьте файл <b>.session</b>", parse_mode="HTML")
        return
    data = await state.get_data()
    phone = data.get("phone")
    if not phone:
        await message.answer(f"{CROSS} Номер не найден. Начните заново.", reply_markup=admin_panel_kb())
        await state.clear()
        return
    file = await message.bot.get_file(message.document.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    result = await account_manager.import_session_file(phone, file_bytes.read(), message.from_user.id, message.bot, api_id=data.get("api_id"), api_hash=data.get("api_hash"))
    if result["status"] == "success":
        text = f"{CHECK} Аккаунт <b>{result['name']}</b> ({phone}) импортирован!" + NL + f"{EYES} ID: {result['id']}"
        await message.answer(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
    else:
        text = f"{CROSS} Ошибка: {result.get('msg', 'Неизвестная ошибка')}"
        await message.answer(text, reply_markup=admin_panel_kb())
    await state.clear()


# === СПИСОК АККАУНТОВ ===
@router.callback_query(F.data == "admin_accounts")
async def cb_accounts_list(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    accounts = db.get_accounts()
    if not accounts:
        await callback.message.edit_text(f"{INFO} Аккаунтов пока нет.", reply_markup=admin_panel_kb())
        return
    text = f"{EYES} <b>Все аккаунты</b>" + NL + NL
    for acc in accounts:
        status_emoji = GREEN_CIRCLE if acc["status"] == "active" else RED_CIRCLE
        flood_info = ""
        if acc["flood_wait_until"] > 0:
            from datetime import datetime
            until = datetime.fromtimestamp(acc["flood_wait_until"])
            flood_info = f" (флуд до {until.strftime('%H:%M')})"
        text += f"{status_emoji} <b>{acc['phone']}</b>" + NL
        text += f"   {GEAR} Статус: {acc['status']}{flood_info}" + NL
        text += f"   {CHART} Нагрузка: {acc['load_count']} | Сегодня: {acc['daily_sent']}" + NL
        text += f"   {CROWN} Премиум: {'Да' if acc['is_premium'] else 'Нет'}" + NL
        text += f"   {EYES} API_ID: {acc.get('api_id', 'не задан')}" + NL + NL
    await callback.message.edit_text(text, reply_markup=account_list_kb(accounts), parse_mode="HTML")


@router.callback_query(F.data.startswith("account_view_"))
async def cb_account_detail(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    acc_id = int(callback.data.split("_")[-1])
    acc = db.get_account(acc_id)
    if not acc:
        await callback.answer(f"{CROSS} Аккаунт не найден", show_alert=True)
        return
    dialogs = await account_manager.get_account_dialogs(acc_id)
    folders_text = ""
    if dialogs:
        folders_text = NL + f"{FOLDER} <b>Чаты:</b>" + NL
        for d in dialogs[:10]:
            folders_text += f"   • {d['title']} ({d['type']})" + NL
        if len(dialogs) > 10:
            folders_text += f"   ... и еще {len(dialogs) - 10}" + NL
    text = f"{GEAR} <b>Аккаунт {acc['phone']}</b>" + NL + NL
    text += f"{EYES} Статус: <code>{acc['status']}</code>" + NL
    text += f"{CHART} Нагрузка: {acc['load_count']}" + NL
    text += f"{SEND} Сегодня: {acc['daily_sent']}" + NL
    text += f"{CROWN} Премиум: {'Да' if acc['is_premium'] else 'Нет'}" + NL
    text += f"{GEAR} API_ID: <code>{acc.get('api_id', 'не задан')}</code>" + NL
    text += f"{WARNING} Flood wait: {acc['flood_wait_until']}" + NL
    text += folders_text
    await callback.message.edit_text(text, reply_markup=account_detail_kb(acc_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("account_refresh_"))
async def cb_account_refresh(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    acc_id = int(callback.data.split("_")[-1])
    await callback.answer(f"{REFRESH} Обновляю...")
    await cb_account_detail(callback)


@router.callback_query(F.data.startswith("account_delete_"))
async def cb_account_delete(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    acc_id = int(callback.data.split("_")[-1])
    await callback.answer(f"{TRASH} Аккаунт удален", show_alert=True)
    await cb_accounts_list(callback)


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    accounts = db.get_accounts()
    total = len(accounts)
    active = len([a for a in accounts if a["status"] == "active"])
    banned = len([a for a in accounts if a["status"] == "banned"])
    flood = len([a for a in accounts if a["status"] == "flood_wait"])
    text = f"{CHART} <b>Статистика</b>" + NL + NL
    text += f"{EYES} Всего: <b>{total}</b>" + NL
    text += f"{GREEN_CIRCLE} Активны: <b>{active}</b>" + NL
    text += f"{RED_CIRCLE} Забанены: <b>{banned}</b>" + NL
    text += f"{WARNING} Flood wait: <b>{flood}</b>" + NL
    await callback.message.edit_text(text, reply_markup=admin_panel_kb(), parse_mode="HTML")
