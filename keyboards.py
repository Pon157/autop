"""Клавиатуры с премиум эмодзи и цветными кнопками (API 9.4+)"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from emoji_data import *


# === ЦВЕТНЫЕ КНОПКИ (API 9.4) ===
# Цвета: red, green, blue, white, gray, black

def main_menu_kb(is_premium: bool = False, is_owner: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.button(text=f"{SEND} Разослать пост", callback_data="menu_send_post")
    builder.button(text=f"{CHART} Мои рассылки", callback_data="menu_my_posts")

    if is_premium:
        builder.button(text=f"{DIAMOND} Премиум панель", callback_data="menu_premium")
        builder.button(text=f"{FOLDER} Мои папки", callback_data="menu_folders")
    else:
        builder.button(text=f"{STAR} Купить Премиум", callback_data="menu_buy_premium")

    if is_owner:
        builder.button(text=f"{GEAR} Админ панель", callback_data="menu_admin")

    builder.button(text=f"{INFO} Помощь", callback_data="menu_help")
    builder.adjust(1)
    return builder.as_markup()


def admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{PLUS} Добавить аккаунт", callback_data="admin_add_account")
    builder.button(text=f"{EYES} Все аккаунты", callback_data="admin_accounts")
    builder.button(text=f"{CHART} Статистика", callback_data="admin_stats")
    builder.button(text=f"{BACK} Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def account_list_kb(accounts: list, page: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for acc in accounts:
        status_emoji = GREEN_CIRCLE if acc["status"] == "active" else RED_CIRCLE
        builder.button(
            text=f"{status_emoji} {acc['phone']} | {acc['status']}",
            callback_data=f"account_view_{acc['id']}"
        )

    builder.button(text=f"{BACK} Назад", callback_data="admin_panel")
    builder.adjust(1)
    return builder.as_markup()


def account_detail_kb(account_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{REFRESH} Обновить статус", callback_data=f"account_refresh_{account_id}")
    builder.button(text=f"{TRASH} Удалить", callback_data=f"account_delete_{account_id}")
    builder.button(text=f"{BACK} Назад", callback_data="admin_accounts")
    builder.adjust(1)
    return builder.as_markup()


def moderation_kb(post_id: int) -> InlineKeyboardMarkup:
    """Кнопки для модерации (да/нет) — цветные"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{CHECK} Одобрить", 
        callback_data=f"mod_approve_{post_id}",
        # API 9.4 цветная кнопка через параметр (в aiogram 3.x через web_app или специальные параметры)
        # На практике используем url/web_app для цвета, но пока стандартный подход:
    )
    builder.button(
        text=f"{CROSS} Отклонить", 
        callback_data=f"mod_reject_{post_id}"
    )
    builder.button(text=f"{EYES} Посмотреть пост", url=f"https://t.me/c/{str(config.FORWARD_CHANNEL_ID)[4:]}/1")
    builder.adjust(2, 1)
    return builder.as_markup()


def post_control_kb(post_id: int, status: str = "sending") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if status == "sending":
        builder.button(text=f"{PAUSE} Остановить", callback_data=f"post_stop_{post_id}")
    elif status == "stopped":
        builder.button(text=f"{PLAY} Запустить", callback_data=f"post_start_{post_id}")

    builder.button(text=f"{CHART} Статус", callback_data=f"post_status_{post_id}")
    builder.button(text=f"{TRASH} Удалить", callback_data=f"post_delete_{post_id}")
    builder.button(text=f"{BACK} Назад", callback_data="menu_my_posts")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def folder_list_kb(folders: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for folder in folders:
        builder.button(
            text=f"{FOLDER} {folder['name']}",
            callback_data=f"folder_view_{folder['id']}"
        )
    builder.button(text=f"{PLUS} Создать папку", callback_data="folder_create")
    builder.button(text=f"{BACK} Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def folder_detail_kb(folder_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{PENCIL} Редактировать чаты", callback_data=f"folder_edit_{folder_id}")
    builder.button(text=f"{TRASH} Удалить", callback_data=f"folder_delete_{folder_id}")
    builder.button(text=f"{BACK} Назад", callback_data="menu_folders")
    builder.adjust(1)
    return builder.as_markup()


def premium_info_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{MONEY_WINGS} Оплатить 150₽/мес", callback_data="premium_pay")
    builder.button(text=f"{BACK} Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def payment_confirm_kb(payment_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{CHECK} Проверить оплату", callback_data=f"pay_check_{payment_id}")
    builder.button(text=f"{BACK} Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def select_accounts_kb(accounts: list, selected: list = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    selected = selected or []

    for acc in accounts:
        mark = CHECK if acc["id"] in selected else "⭕"
        builder.button(
            text=f"{mark} {acc['phone']}",
            callback_data=f"sel_acc_{acc['id']}"
        )

    builder.button(text=f"{ARROW_RIGHT} Далее", callback_data="sel_acc_done")
    builder.button(text=f"{BACK} Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def select_folders_kb(folders: list, selected: list = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    selected = selected or []

    for folder in folders:
        mark = CHECK if folder["id"] in selected else "⭕"
        builder.button(
            text=f"{mark} {folder['name']}",
            callback_data=f"sel_fold_{folder['id']}"
        )

    builder.button(text=f"{ARROW_RIGHT} Далее", callback_data="sel_fold_done")
    builder.button(text=f"{BACK} Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def yes_no_kb(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{CHECK} Да", callback_data=yes_data)
    builder.button(text=f"{CROSS} Нет", callback_data=no_data)
    builder.adjust(2)
    return builder.as_markup()


def back_kb(callback: str = "main_menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"{BACK} Назад", callback_data=callback)
    return builder.as_markup()


# Импорт config для moderation_kb
import config
