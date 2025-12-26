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

# ========= ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ =========

# В Railway / Variables:
# BOT_TOKEN      – токен бота от BotFather
# WEB_APP_URL    – HTTPS-ссылка на игру
# BOT_USERNAME   – username бота без @ (например "anton_runner_bot")
# ADMIN_CHAT_ID  – chat.id твоей лички с ботом (целое число)

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
        print(
            "Внимание: ADMIN_CHAT_ID должно быть целым числом. Сейчас значение:",
            ADMIN_CHAT_ID_RAW,
        )
        ADMIN_CHAT_ID = None

# ========= ЛОГИ =========

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ========= ХЭНДЛЕРЫ КОМАНД =========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /start:
      - в ЛИЧКЕ: показать кнопку WebApp («Играть в игру»).
      - в ГРУППЕ: показать кнопку с deep-link, которая ведёт в личку с ботом.
    """
    chat = update.effective_chat
    user = update.effective_user
    args = context.args or []

    # ЛИЧНЫЙ ЧАТ
    if chat.type == "private":
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

    # ГРУППА / СУПЕРГРУППА
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
                "Чтобы сыграть, отправь /start и нажми «Играть в игру».\n"
                "Игра откроется в личке с ботом.\n"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await update.message.reply_text("Запусти меня в личке или в группе, чтобы сыграть.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот с мини-игрой.\n\n"
        "Как играть:\n"
        "1. В группе: отправь /start и нажми «Играть в игру» — откроется личка с ботом.\n"
        "2. В личке: жми «Играть в игру», запускается окно игры.\n"
    )


# ========= ОБРАБОТКА WEB_APP_DATA =========

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Сюда прилетают ВСЕ сообщения, мы вручную отфильтруем только те,
    где есть web_app_data (данные от WebApp).
    """
    msg = update.effective_message
    if not msg or not msg.web_app_data:
        # Обычное сообщение, не из WebApp – игнорируем
        return

    web_app_data = msg.web_app_data
    user = update.effective_user
    chat = update.effective_chat  # обычно это личка, где запустили игру

    raw_data = web_app_data.data
    logger.info(
        "Получены данные из WebApp от user %s (@%s): %s",
        user.id,
        user.username,
        raw_data,
    )

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        text = (
            f"⚠️ WebApp прислал некорректный JSON от {user.first_name} "
            f"(@{user.username}):\n`{raw_data}`"
        )
        if ADMIN_CHAT_ID is not None:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        return

    # Ожидаемый формат от твоего index.html:
    # { "type": "game_result", "score": <число>, "won": true/false }
    result_type = data.get("type")
    score = data.get("score")
    won = data.get("won")

    if score is None:
        score = 0

    if result_type != "game_result":
        # Неожиданный тип – отправим админу как есть
        text = (
            f"ℹ️ Неизвестный тип web_app_data от {user.first_name} "
            f"(@{user.username}):\n`{raw_data}`"
        )
        if ADMIN_CHAT_ID is not None:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=text,
                parse_mode="Markdown",
            )
        return

    # Формируем текст результата
    if won:
        status_line = "🎉 Победа!"
    else:
        status_line = "😅 Не дошёл(ла) до финала."

    result_text = (
        f"{status_line}\n"
        f"Игрок: {user.first_name} "
        f"(@{user.username or 'без username'}, id={user.id})\n"
        f"Очков: {score}"
    )

    # 1) Игроку – подтверждение
    await context.bot.send_message(
        chat_id=chat.id,
        text="Результат игры отправлен администратору, спасибо за игру!",
        reply_markup=ReplyKeyboardRemove(),
    )

    # 2) Админу – полный результат (если ADMIN_CHAT_ID настроен)
    if ADMIN_CHAT_ID is not None:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=result_text,
        )
    else:
        logger.warning(
            "ADMIN_CHAT_ID не настроен, результат игры от %s (%s) не отправлен админу",
            user.id,
            user.username,
        )


# ========= ЗАПУСК ПРИЛОЖЕНИЯ =========

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Ловим ВСЕ сообщения, внутри web_app_data сами отфильтруем
    application.add_handler(
        MessageHandler(filters.ALL, web_app_data)
    )

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
