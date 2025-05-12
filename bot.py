import logging
import asyncio
import sys
from datetime import datetime
# Telegram
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext
)
# Google Sheets
import gspread
from oauth2client.service_account import ServiceAccountCredentials
# Настройка асинхронного loop для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# Скрытие лишних логов httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение переменных окружения
TOKEN = os.getenv("TOKEN")  # ⬅️ Берётся из переменной окружения
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# Авторизация в Google Sheets
def authorize_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds ', 'https://www.googleapis.com/auth/drive ']
    try:
        if not GOOGLE_CREDENTIALS_JSON:
            logger.error("❌ GOOGLE_CREDENTIALS_JSON не найден в переменных окружения")
            return None

        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        logger.info("✅ Успешно авторизован в Google Sheets")
        return client
    except Exception as e:
        logger.error(f"❌ Ошибка при авторизации в Google Sheets: {e}")
        return None

client = authorize_google_sheets()

# Список администраторов (ID или @username)
ADMINS = [
    "7638667975",         # ID админа (рекомендуется использовать ID)
    "1470547573",
]

# Словарь для отображения ключей на понятные названия
FIELD_NAMES = {
    'fio': 'ФИО',
    'birth_date': 'Дата рождения',
    'age': 'Возраст',
    'driver_license': 'Водительское удостоверение',
    'boat_license': 'Удостоверение на управление лодкой',
    'rent_date': 'Дата аренды',
    'phone_number': 'Телефон'
}

# Состояния диалога
FIO, BIRTH_DATE, DRIVER_LICENSE, BOAT_LICENSE, BOAT_TRAINING, RENT_DATE, PHONE_NUMBER, CONFIRM = range(8)

# Клавиатура для повторной заявки
retry_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔄 Начать заново", callback_data='start_booking')]
])

# Кнопки обучения
training_buttons = ReplyKeyboardMarkup(
    [['✅ Прошёл', '⏳ Ещё не прошёл']],
    one_time_keyboard=True,
    resize_keyboard=True
)

# Кнопки наличия удостоверения на управление маломерным судном
boat_license_buttons = ReplyKeyboardMarkup(
    [['✅ Да', '❌ Нет']],
    one_time_keyboard=True,
    resize_keyboard=True
)

# Приветственное сообщение с кнопкой
async def welcome(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Начать оформление заявки", callback_data='start_booking')],
        [InlineKeyboardButton("📜 Правила управления судном", url='https://64.mchs.gov.ru/uploads/resource/2021-07-01/normativno-pravovye-akty_1625137914639753523.pdf ')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚓️ Добро пожаловать в BoatSharing!\n"
        "Здесь вы можете арендовать маломерное судно и оформить все необходимые документы.\n\n"
        "• Основные правила:\n"
        "• Минимальный возраст — 21 год\n"
        "• Наличие водительских прав — обязательно\n"
        "• Соблюдение всех правил навигации",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

# Начало оформления заявки
async def start_booking(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 Введите ваше ФИО (полностью):")
    return FIO

# ФИО
async def fio(update: Update, context: CallbackContext) -> int:
    context.user_data['fio'] = update.message.text
    await update.message.reply_text("📅 Введите дату рождения и возраст:\nПример: 01.01.1990, 35")
    return BIRTH_DATE

# Дата рождения и возраст
async def birth_date(update: Update, context: CallbackContext) -> int:
    user_input = update.message.text.strip()
    parts = user_input.split(',')
    if len(parts) != 2:
        await update.message.reply_text("⚠️ Неверный формат. Введите дату и возраст через запятую.")
        return BIRTH_DATE
    birth_date_str = parts[0].strip()
    age_str = parts[1].strip()
    try:
        age = int(age_str)
        if age < 21:
            await update.message.reply_text("❌ Вы слишком молоды для аренды судна. Возраст должен быть не менее 21 года.", reply_markup=retry_keyboard)
            return ConversationHandler.END
        context.user_data['birth_date'] = birth_date_str
        context.user_data['age'] = age
        keyboard = [['✅ Да', '❌ Нет']]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("🪪 Есть ли у вас водительское удостоверение?", reply_markup=reply_markup)
        return DRIVER_LICENSE
    except ValueError:
        await update.message.reply_text("⚠️ Неверный формат возраста. Введите целое число.")
        return BIRTH_DATE

# Водительские права
async def driver_license(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.lower()
    context.user_data['driver_license'] = 'ДА' if 'да' in answer else 'НЕТ'
    if context.user_data['driver_license'] == 'НЕТ':
        await update.message.reply_text("❌ Наличие водительского удостоверения обязательно для аренды.", reply_markup=retry_keyboard)
        return ConversationHandler.END
    await update.message.reply_text(
        "🛥 Есть ли у вас удостоверение на право управления маломерным судном?",
        reply_markup=boat_license_buttons
    )
    return BOAT_LICENSE

# Удостоверение на управление маломерным судном
async def boat_license(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.lower()
    context.user_data['boat_license'] = 'ДА' if 'да' in answer else 'НЕТ'
    training_link = "https://64.mchs.gov.ru/uploads/resource/2021-07-01/normativno-pravovye-akty_1625137914639753523.pdf "
    if context.user_data['boat_license'] == 'НЕТ':
        await update.message.reply_text(
            f"🛥 Для аренды судна необходимо пройти обучение:\n{training_link}",
            reply_markup=training_buttons
        )
        return BOAT_TRAINING
    else:
        await update.message.reply_text("📅 Укажите желаемую дату и время аренды:")
        return RENT_DATE

# Обучение по управлению маломерным судном
async def boat_training(update: Update, context: CallbackContext) -> int:
    answer = update.message.text.strip()
    if answer == '✅ Прошёл':
        context.user_data['boat_license'] = 'Прошёл обучение'
        await update.message.reply_text("📅 Укажите желаемую дату и время аренды:")
        return RENT_DATE
    elif answer == '⏳ Ещё не прошёл':
        training_link = "https://64.mchs.gov.ru/uploads/resource/2021-07-01/normativno-pravovye-akty_1625137914639753523.pdf "
        await update.message.reply_text(
            f"🛥 Обучение обязательно. Пройдите его по ссылке:\n{training_link}",
            reply_markup=training_buttons
        )
        return BOAT_TRAINING
    else:
        await update.message.reply_text("⚠️ Пожалуйста, выберите один из вариантов ниже.", reply_markup=training_buttons)
        return BOAT_TRAINING

# Желаемая дата аренды
async def rent_date(update: Update, context: CallbackContext) -> int:
    context.user_data['rent_date'] = update.message.text
    await update.message.reply_text("📱 Введите свой телефонный номер:")
    return PHONE_NUMBER

# Номер телефона
async def phone_number(update: Update, context: CallbackContext) -> int:
    context.user_data['phone_number'] = update.message.text
    summary = (
        "📋 Пожалуйста, проверьте ваши данные:\n\n"
        f"👤 <b>ФИО:</b> {context.user_data['fio']}\n"
        f"🎂 <b>Дата рождения:</b> {context.user_data['birth_date']}\n"
        f"📞 <b>Телефон:</b> {context.user_data['phone_number']}\n"
        f"🪪 <b>Водительские права:</b> {context.user_data['driver_license']}\n"
        f"🛥 <b>Права на лодку:</b> {context.user_data.get('boat_license', '-')}\n"
        f"📅 <b>Дата аренды:</b> {context.user_data['rent_date']}\n"
        "Всё верно?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
        [InlineKeyboardButton("❌ Отменить", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode='HTML')
    return CONFIRM

# Подтверждение или отмена
async def confirm(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    logger.info("🟢 Заявка подтверждена")
    if query.data == 'confirm':
        user = query.from_user
        user_data = context.user_data
        if not client:
            logger.error("❌ Не удалось отправить данные — нет подключения к Google Sheets")
            await query.edit_message_text("⚠️ Произошла внутренняя ошибка. Попробуйте позже.", reply_markup=retry_keyboard)
            return ConversationHandler.END
        try:
            sheet = client.open(GOOGLE_SHEET_NAME).sheet1
            row = [
                datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                user_data['fio'],
                user_data['birth_date'],
                user_data['age'],
                user_data['driver_license'],
                user_data.get('boat_license', '-'),
                user_data['rent_date'],
                user_data['phone_number'],
                f"@{user.username}" if user.username else "Не указан"
            ]
            sheet.append_row(row)
            logger.info(f"✅ Заявка успешно сохранена: {row}")

            # Формируем текст уведомления
            summary_text = "🔔 Получена новая заявка:\n\n"
            for key, value in user_data.items():
                display_name = FIELD_NAMES.get(key, key)
                summary_text += f"{display_name}: {value}\n"

            # Рассылаем всем админам
            for admin in ADMINS:
                try:
                    await context.bot.send_message(chat_id=admin, text=summary_text)
                    logger.info(f"📩 Уведомление отправлено администратору: {admin}")
                except Exception as e:
                    logger.error(f"❌ Не удалось отправить уведомление администратору {admin}: {e}")

            await query.edit_message_text(
                "✅ <b>Ваша заявка успешно оформлена!</b>\n\n"
                "Наш менеджер свяжется с вами в ближайшее время.\n"
                "Время работы: с 9:00 до 19:00\n\n"
                "Перед использованием судна ознакомьтесь с правилами:\n"
                "https://64.mchs.gov.ru/uploads/resource/2021-07-01/normativno-pravovye-akty_1625137914639753523.pdf ",
                parse_mode='HTML',
                reply_markup=retry_keyboard
            )
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении: {e}")
            await query.edit_message_text("⚠️ Ошибка при сохранении данных.", reply_markup=retry_keyboard)
    else:
        await query.edit_message_text("❌ Заявка отменена.", reply_markup=retry_keyboard)
    return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Заявка отменена.", reply_markup=retry_keyboard)
    return ConversationHandler.END

# Хэндлер для случайных сообщений
async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "⚠️ Я не понимаю это сообщение.\n"
        "Нажмите \"Начать оформление заявки\", чтобы продолжить.",
        reply_markup=retry_keyboard
    )

# Диалог
conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_booking, pattern='^start_booking$')],
    states={
        FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, fio)],
        BIRTH_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, birth_date)],
        DRIVER_LICENSE: [MessageHandler(filters.Regex('^(✅ Да|❌ Нет)$'), driver_license)],
        BOAT_LICENSE: [MessageHandler(filters.Regex('^(✅ Да|❌ Нет)$'), boat_license)],
        BOAT_TRAINING: [MessageHandler(filters.Regex('^(✅ Прошёл|⏳ Ещё не прошёл)$'), boat_training)],
        RENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, rent_date)],
        PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_number)],
        CONFIRM: [CallbackQueryHandler(confirm, pattern='^(confirm|cancel)$')]
    },
    fallbacks=[
        MessageHandler(filters.TEXT & ~filters.COMMAND, welcome),
        MessageHandler(filters.COMMAND, welcome),
        CallbackQueryHandler(start_booking, pattern='^start_booking$')
    ],
    per_message=False
)

# Запуск бота
def main():
    if not TOKEN:
        logger.error("❌ TOKEN не установлен в переменных окружения")
        return
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & filters.COMMAND, welcome))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, welcome))
    logger.info("🚀 Бот запущен")
    application.run_polling()

if __name__ == '__main__':
    main()
