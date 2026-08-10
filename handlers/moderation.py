"""Модерация постов — одобрение/отклонение"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from database import db
from keyboards import *
from emoji_data import *

router = Router()


@router.callback_query(F.data.startswith("mod_approve_"))
async def cb_mod_approve(callback: CallbackQuery):
    if callback.from_user.id not in config.OWNER_IDS:
        await callback.answer(f"{STOP} Нет доступа!", show_alert=True)
        return
    post_id = int(callback.data.split("_")[-1])
    post = db.get_post(post_id)
    if not post:
        await callback.answer(f"{CROSS} Пост не найден", show_alert=True)
        return
    if post["status"] != "pending":
        await callback.answer(f"{INFO} Пост уже обработан", show_alert=True)
        return
    db.update_post_status(post_id, "approved")
    try:
        builder = InlineKeyboardBuilder()
        builder.button(text=f"{GEAR} Настроить рассылку", callback_data=f"post_setup_{post_id}")
        builder.button(text=f"{BACK} Главное меню", callback_data="main_menu")
        builder.adjust(1)
        text = f"{CHECK} <b>Ваш пост одобрен!</b>" + "\n\n"
        text += f"{ARROW_RIGHT} Теперь настройте аккаунты и чаты для рассылки."
        await callback.bot.send_message(post["user_id"], text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        print(f"[Moderation] Ошибка уведомления пользователя: {e}")
    text = f"{CHECK} <b>Пост #{post_id} одобрен</b>" + "\n"
    text += f"{EYES} Пользователь уведомлен."
    await callback.message.edit_text(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("mod_reject_"))
async def cb_mod_reject(callback: CallbackQuery):
    if callback.from_user.id not in config.OWNER_IDS:
        await callback.answer(f"{STOP} Нет доступа!", show_alert=True)
        return
    post_id = int(callback.data.split("_")[-1])
    post = db.get_post(post_id)
    if not post:
        await callback.answer(f"{CROSS} Пост не найден", show_alert=True)
        return
    db.update_post_status(post_id, "rejected")
    try:
        text = f"{CROSS} <b>Ваш пост отклонен</b>" + "\n\n"
        text += f"{INFO} Обратитесь к администратору для уточнения причин."
        await callback.bot.send_message(post["user_id"], text, parse_mode="HTML")
    except Exception as e:
        print(f"[Moderation] Ошибка уведомления: {e}")
    await callback.message.edit_text(f"{CROSS} <b>Пост #{post_id} отклонен</b>", parse_mode="HTML")
