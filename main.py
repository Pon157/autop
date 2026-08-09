"""
Telegram Auto Sender Bot
Авторассылка постов с модерацией и монетизацией
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import config
from database import db
from telethon_manager import account_manager
from handlers import get_routers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def main():
    # Инициализация бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Регистрация роутеров
    for router in get_routers():
        dp.include_router(router)

    # Загрузка сессий Telethon
    logger.info("Загрузка Telethon сессий...")
    await account_manager.load_sessions()

    # Запуск мониторинга
    logger.info("Запуск мониторинга аккаунтов...")
    await account_manager.start_monitoring()

    # Запуск бота
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

    # Очистка
    await account_manager.disconnect_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
