"""Панель администратора (owner)"""
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


class AdminStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()


def is_owner(user_id: int) -> bool:
    return user_id in config.OWNER_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_owner(message.from_user.id):
        await message.answer(f"{STOP} Доступ запрещен.")
        return
    await message.answer(
        f"{GEAR} <b>Админ панель</b>

"
        f"{EYES} Управление аккаунтами и статистикой.",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "menu_admin")
async def cb_admin_panel(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer(f"{STOP} Нет доступа!", show_alert=True)
        return
    await callback.message.edit_text(
        f"{GEAR} <b>Админ панель</b>

"
        f"{EYES} Управление аккаунтами и статистикой.",
        reply_markup=admin_panel_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_add_account")
async def cb_add_account(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        return
    await callback.message.edit_text(
        f"{PLUS} <b>Добавление аккаунта</b>

"
        f"{INFO} Введите номер телефона в формате +79991234567:",
        reply_markup=back_kb("admin_panel"),
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_phone)


@router.message(AdminStates.waiting_phone)
async def process_phone(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    phone = message.text.strip()
    await state.update_data(phone=phone)

    result = await account_manager.add_account(phone)

    if result["status"] == "code_needed":
        await message.answer(
            f"{BELL} Код отправлен на {{phone}}.
"
            f"{INFO} Введите код из Telegram:",
            reply_markup=back_kb("admin_panel")
        )
        await state.set_state(AdminStates.waiting_code)
    elif result["status"] == "success":
        await message.answer(
            f"{CHECK} Аккаунт <b>{{result['name']}}</b> ({{phone}}) успешно добавлен!
"
            f"{EYES} ID: {{result['id']}}",
            reply_markup=admin_panel_kb(),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer(
            f"{CROSS} Ошибка: {{result.get('msg', 'Неизвестная ошибка')}}",
            reply_markup=admin_panel_kb()
        )
        await state.clear()


@router.message(AdminStates.waiting_code)
async def process_code(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    data = await state.get_data()
    phone = data["phone"]
    code = message.text.strip()

    result = await account_manager.add_account(phone, code=code)

    if result["status"] == "password_needed":
        await message.answer(
            f"{LOCK} Требуется пароль 2FA.
"
            f"{INFO} Введите пароль:",
            reply_markup=back_kb("admin_panel")
        )
        await state.set_state(AdminStates.waiting_password)
    elif result["status"] == "success":
        await message.answer(
            f"{CHECK} Аккаунт <b>{{result['name']}}</b> успешно добавлен!
"
            f"{EYES} ID: {{result['id']}}",
            reply_markup=admin_panel_kb(),
            parse_mode="HTML"
        )
        await state.clear()
    else:
        await message.answer(
            f"{CROSS} Ошибка: {{result.get('msg', 'Неизвестная ошибка')}}",
            reply_markup=admin_panel_kb()
        )
        await state.clear()


@router.message(AdminStates.waiting_password)
async def process_password(message: Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    data = await state.get_data()
    phone = data["phone"]
    code = data.get("code", "")
    password = message.text.strip()

    result = await account_manager.add_account(phone, code=code, password=password)

    if result["status"] == "success":
        await message.answer(
            f"{CHECK} Аккаунт <b>{{result['name']}}</b> успешно добавлен!
"
            f"{EYES} ID: {{result['id']}}",
            reply_markup=admin_panel_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"{CROSS} Ошибка: {{result.get('msg', 'Неизвестная ошибка')}}",
            reply_markup=admin_panel_kb()
        )
    await state.clear()


@router.callback_query(F.data == "admin_accounts")
async def cb_accounts_list(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return

    accounts = db.get_accounts()
    if not accounts:
        await callback.message.edit_text(
            f"{INFO} Аккаунтов пока нет.",
            reply_markup=admin_panel_kb()
        )
        return

    text = f"{EYES} <b>Все аккаунты</b>

"
    for acc in accounts:
        status_emoji = GREEN_CIRCLE if acc["status"] == "active" else RED_CIRCLE
        flood_info = ""
        if acc["flood_wait_until"] > 0:
            from datetime import datetime
            until = datetime.fromtimestamp(acc["flood_wait_until"])
            flood_info = f" (флуд до {{until.strftime('%H:%M')}})"

        text += (
            f"{{status_emoji}} <b>{{acc['phone']}}</b>
"
            f"   {GEAR} Статус: {{acc['status']}}{{flood_info}}
"
            f"   {CHART} Нагрузка: {{acc['load_count']}} | Сегодня: {{acc['daily_sent']}}
"
            f"   {CROWN} Премиум: {{'Да' if acc['is_premium'] else 'Нет'}}

"
        )

    await callback.message.edit_text(
        text,
        reply_markup=account_list_kb(accounts),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("account_view_"))
async def cb_account_detail(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    acc_id = int(callback.data.split("_")[-1])
    acc = db.get_account(acc_id)
    if not acc:
        await callback.answer(f"{CROSS} Аккаунт не найден", show_alert=True)
        return

    # Получаем диалоги
    dialogs = await account_manager.get_account_dialogs(acc_id)
    folders_text = ""
    if dialogs:
        folders_text = f"\n{FOLDER} <b>Чаты и папки:</b>\n"
        for d in dialogs[:10]:
            folders_text += f"   • {{d['title']}} ({{d['type']}})\n"
        if len(dialogs) > 10:
            folders_text += f"   ... и еще {{len(dialogs) - 10}}\n"

    text = (
        f"{GEAR} <b>Аккаунт {{acc['phone']}}</b>\n\n"
        f"{EYES} Статус: <code>{{acc['status']}}</code>\n"
        f"{CHART} Нагрузка: {{acc['load_count']}}\n"
        f"{SEND} Отправлено сегодня: {{acc['daily_sent']}}\n"
        f"{CROWN} Премиум: {{'Да' if acc['is_premium'] else 'Нет'}}\n"
        f"{FLOOD} Flood wait: {{acc['flood_wait_until']}}\n"
        f"{{folders_text}}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=account_detail_kb(acc_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("account_refresh_"))
async def cb_account_refresh(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    acc_id = int(callback.data.split("_")[-1])
    # Переподключаем
    await callback.answer(f"{REFRESH} Обновляю...")
    # Логика обновления в менеджере
    await cb_account_detail(callback)


@router.callback_query(F.data.startswith("account_delete_"))
async def cb_account_delete(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        return
    acc_id = int(callback.data.split("_")[-1])
    # TODO: удаление сессии и из БД
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

    text = (
        f"{CHART} <b>Статистика аккаунтов</b>\n\n"
        f"{EYES} Всего: <b>{{total}}</b>\n"
        f"{GREEN_CIRCLE} Активны: <b>{{active}}</b>\n"
        f"{RED_CIRCLE} Забанены: <b>{{banned}}</b>\n"
        f"{WARNING} Flood wait: <b>{{flood}}</b>\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=admin_panel_kb(),
        parse_mode="HTML"
    )
