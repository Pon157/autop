"""Обработчики бота"""
from aiogram import Router

from . import admin, user, moderation, payments


def get_routers() -> list[Router]:
    return [
        admin.router,
        user.router,
        moderation.router,
        payments.router,
    ]
