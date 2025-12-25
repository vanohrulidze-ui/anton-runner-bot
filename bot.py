import os
import json
import logging

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ========= НАСТРОЙКИ =========

# В Railway в Variables должны быть:
# BOT_TOKEN  – токен бота от BotFather
# WEB_APP_URL – HTTPS-ссылка на твою игру (GitHub Pages / Netlify)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL")

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения")
if not WEB_APP_URL:
    raise RuntimeError("Не задан WEB_APP_URL в переменных окружения")

# ========= ЛОГИ =========

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ========= ХЭНДЛЕРЫ =========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start в личке или в чате:
    показываем кнопку "Играть в игру", которая открывает WebApp.
    """
    keyboard = [[
        KeyboardButton(
            text="Играть в игру",
            web_app=WebAppInfo(url=WEB_APP_URL),
        )
    ]]

    await update.message.reply_text(
        "Нажми кнопку, чтобы запустить игру.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=False,
        ),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /help – простая подсказка.
    """
    await update.message.reply_text(
        "Я бот с мини-игрой.\n\n"
        "1) Нажми /start\n"
        "2) Нажми «Играть в игру»\n"
        "3) Пройди игру – результат появится в чате."
    )


async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Сервисное сообщение от WebApp.
    Сюда прилетает JSON, который отправила игра через Telegram.WebApp.sendData().
    """
    msg = update.effective_message
    web_app_data = msg.web_app_data
    user = update.effective_user
    chat = update.effective_chat

    # На всякий случай проверим
    if not web_app_data:
        logger.warning("Получено сообщение WEB_APP_DATA, но web_app_data пустой")
        return

    raw_data = web_app_data.data
    logger.info("Получены данные из WebApp: %s", raw_data)

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"{user.first_name} сыграл(а) в игру, но данные повреждены.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Ожидаем формат:
    # {
    #   "score": 120,
    #   "finished": true/false,
    #   "obstacles_passed": 15
    # }
    score = data.get("score")
    finished = data.get("finished")
    obstacles_passed = data.get("obstacles_passed")

    # Подстрахуемся, если чего-то нет
    if score is None:
        score = 0
    if obstacles_passed is None:
        obstacles_passed = 0

    if finished:
        text = (
            f"{user.first_name} прошёл(ла) игру и победил(а)! 🎉\n"
            f"Препятствий пройдено: {obstacles_passed}\n"
            f"Очков: {score}"
        )
    else:
        text = (
            f"{user.first_name} не дошёл(ла) до финала.\n"
            f"Препятствий пройдено: {obstacles_passed}\n"
            f"Очков: {score}"
        )

    await context.bot.send_message(
        chat_id=chat.id,
        text=text,
        reply_markup=ReplyKeyboardRemove(),  # можно убрать клавиатуру после игры
    )


def main() -> None:
    """
    Точка входа.
    """
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Обработка данных из WebApp
    application.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data)
    )

    # Запускаем бота (long polling)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
