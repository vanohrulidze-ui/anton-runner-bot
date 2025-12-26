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

# ========== НАСТРОЙКИ И ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ==========

# В Railway / Variables должны быть:
# BOT_TOKEN      – токен бота от BotFather
# WEB_APP_URL    – HTTPS-ссылка на твою игру (GitHub Pages / Vercel / Netlify и т.п.)
# BOT_USERNAME   – username бота без @ (например "anton_runner_bot")
# ADMIN_CHAT_ID  – chat.id твоего личного чата с ботом (целое число)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEB_APP_URL = os.environ.get("WEB_APP_URL")
BOT_USERNAME = os.environ.get("BOT_USERNAME")
ADMIN_CHAT_ID_RAW = os.environ.get("ADMIN_CHAT_ID")

if not BOT_TOKEN:
  raise RuntimeError("Не задан BOT_TOKEN в переменных окружения")
if not WEB_APP_URL:
  raise RuntimeError("Не задан WEB_APP_URL в переменных окружения")
if not BOT_USERNAME:
  raise RuntimeError("Не задан BOT_USERNAME в переменных окружения")
if not ADMIN_CHAT_ID_RAW:
  raise RuntimeError("Не задан ADMIN_CHAT_ID в переменных окружения")

try:
  ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_RAW)
except ValueError:
  raise RuntimeError("ADMIN_CHAT_ID должен быть целым числом (chat.id твоего чата с ботом)")

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
    - в ЛИЧКЕ: показывает клавиатуру с кнопкой WebApp («Играть в игру»).
    - в ГРУППЕ: показывает inline-кнопку с deep-link, ведущим в личку с ботом.
  """
  chat = update.effective_chat
  user = update.effective_user
  args = context.args or []
    
    # >>> ВРЕМЕННЫЙ ВСТАВЛЕННЫЙ КУСОК <<<
    # Просто показать тебе chat.id того чата, где ты написал /start
    if update.message:
        await update.message.reply_text(f"Этот chat.id: {chat.id}")
    # <<< КОНЕЦ ВРЕМЕННОГО КУСОЧКА >>>

  # ЛИЧНЫЙ ЧАТ
  if chat.type == "private":
    # Параметр /start group_<chat_id> можно при желании использовать — сейчас он
    # ни на что не влияет, т.к. результаты мы шлём только админу.
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
    # ссылка вида https://t.me/<bot_username>?start=group_<chat_id>
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
        "а результат будет отправлен администратору."
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
    "3) Результаты всех игр отправляются администратору бота."
  )


# ========== ОБРАБОТКА ДАННЫХ ИЗ WEBAPP ==========

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
  """
  Сервисное сообщение от WebApp.
  Сюда прилетает JSON, который отправила игра через Telegram.WebApp.sendData().
  """
  msg = update.effective_message
  web_app_data = msg.web_app_data
  user = update.effective_user
  chat = update.effective_chat  # это, как правило, личка, откуда запускалась WebApp

  # На всякий случай проверим
  if not web_app_data:
    logger.warning("Получено сообщение WEB_APP_DATA, но web_app_data пустой")
    return

  raw_data = web_app_data.data
  logger.info("Получены данные из WebApp от user %s (%s): %s", user.id, user.username, raw_data)

  try:
    data = json.loads(raw_data)
  except json.JSONDecodeError:
    # Сообщение админу о битых данных
    text = (
      f"⚠️ WebApp прислал некорректный JSON от пользователя {user.first_name} (@{user.username}):\n"
      f"`{raw_data}`"
    )
    await context.bot.send_message(
      chat_id=ADMIN_CHAT_ID,
      text=text,
      parse_mode="Markdown",
    )
    return

  # Структура data зависит от того, что ты отправляешь из WebApp
  # Например:
  # {
  #   "type": "game_result",
  #   "score": 123,
  #   "won": true,
  #   "obstacles_passed": 20
  # }

  result_type = data.get("type")
  score = data.get("score")
  won = data.get("won")
  obstacles_passed = data.get("obstacles_passed")

  if result_type != "game_result":
    # На всякий случай логируем неизвестный тип
    logger.info("Неизвестный тип web_app_data: %r", result_type)
    text = (
      f"ℹ️ Получены данные неизвестного типа от {user.first_name} (@{user.username}):\n"
      f"`{raw_data}`"
    )
    await context.bot.send_message(
      chat_id=ADMIN_CHAT_ID,
      text=text,
      parse_mode="Markdown",
    )
    return

  # Формируем человекочитаемый текст результата
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

  # ВОТ ЗДЕСЬ ГЛАВНАЯ ЛОГИКА:
  # Отправляем результат ТОЛЬКО АДМИНУ в личку (в чат ADMIN_CHAT_ID).
  await context.bot.send_message(
    chat_id=ADMIN_CHAT_ID,
    text=text,
  )

  # Если хочешь дополнительно показывать короткое сообщение игроку – раскомментируй:
  # await context.bot.send_message(
  #     chat_id=chat.id,
  #     text="Результат игры отправлен администратору, спасибо за игру!",
  #     reply_markup=ReplyKeyboardRemove(),
  # )


# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========

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
