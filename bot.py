import os
import json
import logging

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ========== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ==========

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
ADMIN_CHAT_ID_RAW = os.environ.get("ADMIN_CHAT_ID")  # может быть не задан

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в переменных окружения")
if not WEB_APP_URL:
    raise RuntimeError("Не задан WEB_APP_URL в переменных окружения")
if not BOT_USERNAME:
    raise RuntimeError("Не задан BOT_USERNAME в переменных окружения")

ADMIN_CHAT_ID = None
if ADMIN_CHAT_ID_RAW:
    try:
        ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_RAW)
    except ValueError:
        # Не валидное значение – просто логируем, но бот всё равно запускается
        print("Внимание: ADMIN_CHAT_ID должно быть целым числом. Сейчас значение:", ADMIN_CHAT_ID_RAW)
        ADMIN_CHAT_ID = None

# ========== ЛОГИРОВАНИЕ ==========

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start:
      - в ЛИЧКЕ: показывает клавиатуру с WebApp («Играть в игру») + пишет chat.id.
      - в ГРУППЕ: показывает inline-кнопку с deep-link, ведущим в личку с ботом.
    """
    chat = update.effective_chat
    user = update.effective_user
    args = context.args or []

    # ВРЕМЕННО: всегда показываем chat.id, чтобы ты точно его увидел
    if update.message:
        await update.message.reply_text(f"Этот chat.id: {chat.id}")

    # ЛИЧНЫЙ ЧАТ
    if chat.type == "private":
        # Параметр /start group_<chat_id> сейчас логируем для информации, но не используем
        if args:
            logger.info("Личный /start от %s с параметром: %s", user.id, args[0])

        keyboard = [[
            KeyboardButton(
                text="Играть в игру",
                web_app=WebAppInfo(url=WEB_APP_URL),
            )
        ]]

        await update.message.reply_text(
            "Нажми «Играть в игру», чтобы запустить мини-игру.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=False,
            ),
        )
        return

    # ГРУППА / СУПЕРГРУППА: показываем deep-link кнопку
    if chat.type in ("group", "supergroup"):
        deep_link = f"https://t.me/{BOT_USERNAME}?start=group_{chat.id}"

        keyboard = [[
            InlineKeyboardButton(
                text="Играть в игру",
                url=deep_link,
            )
        ]]

        await update.message.reply_text(
            (
                "Чтобы сыграть, нажми «Играть в игру».\n"
                "Игра откроется в личке с ботом, "
                "а результат будет отправлен администратору (если настроен ADMIN_CHAT_ID)."
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # На всякий случай — другие типы чатов (каналы и т.п.)
    await update.message.reply_text("Запусти меня в личке или в группе, чтобы сыграть.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /help – простая подсказка.
    """
    await update.message.reply_text(
        "Я бот с мини-игрой.\n\n"
        "Как играть:\n"
        "1) В группе: отправь /start и нажми кнопку «Играть в игру» — откроется личка с ботом.\n"
        "2) В личке: жми «Играть в игру», запускается окно игры.\n"
        "3) Если ADMIN_CHAT_ID настроен, все результаты игр отправляются администратору."
    )


# ========== ОБРАБОТКА ДАННЫХ ИЗ WEBAPP ==========

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Сюда прилетает JSON от игры (Telegram.WebApp.sendData()).
    Отправляем результат админу, если ADMIN_CHAT_ID настроен.
    """
    msg = update.effective_message
    web_app_data = msg.web_app_data
    user = update.effective_user
    chat = update.effective_chat  # обычно это личка, где запустили WebApp

    if not web_app_data:
        logger.warning("Получено WEB_APP_DATA, но web_app_data пустой")
        return

    raw_data = web_app_data.data
    logger.info("Получены данные из WebApp от user %s (%s): %s", user.id, user.username, raw_data)

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        text = (
            f"⚠️ WebApp прислал некорректный JSON от {user.first_name} (@{user.username}):\n"
            f"`{raw_data}`"
        )
        if ADMIN_CHAT_ID is not None:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        return

    result_type = data.get("type")
    score = data.get("score")
    won = data.get("won")
    obstacles_passed = data.get("obstacles_passed")

    if result_type != "game_result":
        logger.info("Неизвестный тип web_app_data: %r", result_type)
        text = (
            f"ℹ️ Получены данные неизвестного типа от {user.first_name} (@{user.username}):\n"
            f"`{raw_data}`"
        )
        if ADMIN_CHAT_ID is not None:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        return

    # Формируем текст
    if won:
        status_line = "🎉 Победа!"
    else:
        status_line = "😅 Не дошёл(ла) до финала."

    text_lines = [
        f"{status_line}",
        f"Игрок: {user.first_name} (@{user.username or 'без username'}, id={user.id})",
    ]
    if obstacles_passed is not None:
        text_lines.append(f"Препятствий пройдено: {obstacles_passed}")
    if score is not None:
        text_lines.append(f"Очков: {score}")

    text = "\n".join(text_lines)

    # 1) Игроку – короткое подтверждение (по желанию)
    await context.bot.send_message(
        chat_id=chat.id,
        text="Результат игры отправлен администратору, спасибо за игру!",
        reply_markup=ReplyKeyboardRemove(),
    )

    # 2) Админу – подробный результат (если настроен ADMIN_CHAT_ID)
    if ADMIN_CHAT_ID is not None:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=text,
        )
    else:
        # Если ADMIN_CHAT_ID не настроен – просто логируем
        logger.warning("ADMIN_CHAT_ID не настроен, результат игры некуда отправить администратору.")


# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Данные из WebApp
    application.add_handler(
        MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data)
    )

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
