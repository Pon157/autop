"""Монетизация — ЮKassa"""
import uuid
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery

import config
from database import db
from keyboards import *
from emoji_data import *

router = Router()

try:
    from yookassa import Configuration, Payment
    Configuration.account_id = config.YOOKASSA_SHOP_ID
    Configuration.secret_key = config.YOOKASSA_SECRET_KEY
    YOOKASSA_ENABLED = bool(config.YOOKASSA_SHOP_ID and config.YOOKASSA_SECRET_KEY)
except ImportError:
    YOOKASSA_ENABLED = False


@router.callback_query(F.data == "menu_buy_premium")
async def cb_buy_premium(callback: CallbackQuery):
    text = f"{DIAMOND} <b>Премиум рассылка</b>" + "\n\n"
    text += f"{STAR} <b>Преимущества:</b>" + "\n"
    text += f"{CHECK} Выделенный аккаунт" + "\n"
    text += f"{CHECK} Нет очереди на рассылку" + "\n"
    text += f"{CHECK} Настройка интервалов (до 20 сек)" + "\n"
    text += f"{CHECK} Собственные папки чатов" + "\n"
    text += f"{CHECK} Приоритетная модерация" + "\n\n"
    text += f"{MONEY} <b>Стоимость:</b> <code>150 ₽/месяц</code>"
    await callback.message.edit_text(text, reply_markup=premium_info_kb(), parse_mode="HTML")


@router.callback_query(F.data == "premium_pay")
async def cb_premium_pay(callback: CallbackQuery):
    if not YOOKASSA_ENABLED:
        await callback.answer(f"{CROSS} Платежная система временно недоступна.", show_alert=True)
        return
    user_id = callback.from_user.id
    payment_id = str(uuid.uuid4())
    try:
        payment = Payment.create({
            "amount": {"value": str(config.PREMIUM_PRICE), "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": f"https://t.me/{(await callback.bot.me()).username}"},
            "capture": True,
            "description": f"Премиум подписка на 1 месяц (User: {user_id})",
            "metadata": {"user_id": str(user_id), "payment_db_id": payment_id}
        })
        db.add_payment(user_id, payment.id, config.PREMIUM_PRICE)
        text = f"{MONEY_WINGS} <b>Оплата Премиума</b>" + "\n\n"
        text += f"{INFO} Перейдите по ссылке для оплаты:" + "\n"
        text += f"{LINK} <a href=\"{payment.confirmation.confirmation_url}\">Оплатить 150 ₽</a>" + "\n\n"
        text += f"{CHECK} После оплаты нажмите кнопку ниже:"
        await callback.message.edit_text(text, reply_markup=payment_confirm_kb(payment.id), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        await callback.answer(f"{CROSS} Ошибка: {str(e)[:100]}", show_alert=True)


@router.callback_query(F.data.startswith("pay_check_"))
async def cb_check_payment(callback: CallbackQuery):
    if not YOOKASSA_ENABLED:
        await callback.answer(f"{CROSS} ЮKassa не настроена", show_alert=True)
        return
    yookassa_id = callback.data.split("_", 2)[-1]
    try:
        payment = Payment.find_one(yookassa_id)
        if payment.status == "succeeded":
            db.update_payment(yookassa_id, "succeeded")
            user_id = callback.from_user.id
            until = datetime.now() + timedelta(days=30)
            db.set_premium(user_id, until)
            for owner_id in config.OWNER_IDS:
                try:
                    text = f"{BELL} <b>Новая Премиум покупка!</b>" + "\n\n"
                    text += f"{EYES} Пользователь: <a href=\"tg://user?id={user_id}\">{user_id}</a>" + "\n"
                    text += f"{MONEY} Сумма: 150 ₽" + "\n\n"
                    text += f"{INFO} Добавьте выделенный аккаунт для этого пользователя."
                    await callback.bot.send_message(owner_id, text, parse_mode="HTML")
                except Exception as e:
                    print(f"[Payment] Ошибка уведомления owner: {e}")
            text = f"{CHECK} <b>Оплата прошла успешно!</b>" + "\n\n"
            text += f"{DIAMOND} Премиум активирован до <b>{until.strftime('%d.%m.%Y')}</b>" + "\n"
            text += f"{INFO} Администратор добавит вам выделенный аккаунт." + "\n"
            text += f"{BELL} Вы получите уведомление, когда аккаунт будет готов."
            await callback.message.edit_text(text, reply_markup=main_menu_kb(is_premium=True), parse_mode="HTML")
        elif payment.status == "pending":
            await callback.answer(f"{HOURGLASS} Платеж еще обрабатывается. Попробуйте позже.", show_alert=True)
        else:
            await callback.answer(f"{CROSS} Платеж отменен или не завершен.", show_alert=True)
    except Exception as e:
        await callback.answer(f"{CROSS} Ошибка проверки: {str(e)[:100]}", show_alert=True)
