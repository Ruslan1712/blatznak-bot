# -*- coding: utf-8 -*-
import os
import logging
import re
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN") or "7799074981:AAEBfZZ48qJmcR1srEOk3GRTfT5PgFP-Z_g"
CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blat-znak-63d9713dc5ce.json")

# === Транслитерация ===
def ru_to_lat(text):
    repl = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")
    return text.translate(repl)

# === Google Sheets ===
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

def get_all_numbers():
    """Читает все номера со всех листов Google Sheets (кроме 'Номера')"""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open("все_номера_для_бота")
        all_rows = []
        skip_sheets = {"Номера"}
        for worksheet in spreadsheet.worksheets():
            if worksheet.title in skip_sheets:
                continue
            rows = worksheet.get_all_values()
            if len(rows) > 1:
                all_rows.extend(rows[1:])  # пропускаем заголовок
        return all_rows
    except Exception as e:
        logger.error(f"Ошибка чтения Google Sheets: {e}")
        return []

def get_sheet_data(sheet_name):
    """Читает данные с конкретного листа"""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open("все_номера_для_бота")
        worksheet = spreadsheet.worksheet(sheet_name)
        rows = worksheet.get_all_values()
        return rows[1:] if len(rows) > 1 else []
    except Exception as e:
        logger.error(f"Ошибка чтения листа {sheet_name}: {e}")
        return []

def format_row(row):
    """Форматирует строку номера для отображения"""
    try:
        number = row[0].strip() if len(row) > 0 else ""
        region = row[1].strip() if len(row) > 1 else ""
        price = row[2].strip() if len(row) > 2 else ""
        note = row[3].strip() if len(row) > 3 else ""
        if not number:
            return None
        parts = [f"{number}"]
        if region:
            parts[0] += f" {region}"
        if price:
            parts.append(f"{price}₽")
        if note:
            parts.append(note)
        return " - ".join(parts)
    except:
        return None

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup([
        ["🔁 Старт"],
        ["🔍 Поиск номера по цифрам", "🔠 Поиск номера по буквам"],
        ["🛵 Мото номера", "🚛 Прицеп номера"],
        ["📍 Москва все номера", "📍 Московская обл. все номера"],
        ["🛠 Наши услуги", "📞 Наш адрес и контакты"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "Добро пожаловать в компанию BlatZnak!\n"
        "Мы занимаемся продажей гос номеров и постановкой на учет.\n"
        "Выберите действие:",
        reply_markup=keyboard
    )

# === Показать лист целиком ===
async def send_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet_name: str):
    rows = get_sheet_data(sheet_name)
    if not rows:
        await update.message.reply_text("Номера не найдены.")
        return
    lines = []
    for row in rows:
        line = format_row(row)
        if line:
            lines.append(line)
    content = "\n".join(lines)
    if not content:
        await update.message.reply_text("Номера не найдены.")
        return
    for i in range(0, len(content), 4000):
        await update.message.reply_text(content[i:i+4000])

# === Универсальный обработчик ===
async def unified_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_data = context.user_data

    if text == "🔁 Старт":
        await start(update, context)
        return

    elif text == "🔠 Поиск номера по буквам":
        user_data["expecting_letter_search"] = True
        user_data["expecting_digit_search"] = False
        await update.message.reply_text("Введите буквы для поиска (например, МК или АА):")
        return

    elif user_data.get("expecting_letter_search"):
        query = ru_to_lat(text.upper())
        user_data["expecting_letter_search"] = False
        all_rows = get_all_numbers()
        results = []
        for row in all_rows:
            if not row or not row[0].strip():
                continue
            only_letters = ru_to_lat("".join(re.findall(r"[А-ЯA-Z]+", row[0].upper())))
            if query in only_letters:
                line = format_row(row)
                if line:
                    results.append(line)
        if results:
            reply = "\n".join(results)
            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i:i+4000])
        else:
            await update.message.reply_text("❗ Номеров с такими буквами не найдено.")
        return

    elif text == "🔍 Поиск номера по цифрам":
        user_data["expecting_digit_search"] = True
        user_data["expecting_letter_search"] = False
        await update.message.reply_text("Введите цифры для поиска (например, 777 или 007):")
        return

    elif user_data.get("expecting_digit_search"):
        digits = text
        user_data["expecting_digit_search"] = False
        all_rows = get_all_numbers()
        results = []
        for row in all_rows:
            if not row or not row[0].strip():
                continue
            if digits in row[0]:
                line = format_row(row)
                if line:
                    results.append(line)
        if results:
            reply = "\n".join(results)
            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i:i+4000])
        else:
            await update.message.reply_text("❗ Номеров с такими цифрами не найдено.")
        return

    elif text == "🛵 Мото номера":
        await send_sheet(update, context, "Мото")

    elif text == "🚛 Прицеп номера":
        await send_sheet(update, context, "Прицеп")

    elif text == "📍 Москва все номера":
        await send_sheet(update, context, "Москва")

    elif text == "📍 Московская обл. все номера":
        await send_sheet(update, context, "Московская область")

    elif text == "🛠 Наши услуги":
        await update.message.reply_text(
            "📌 Наши услуги:\n"
            "- Дубликат номеров\n"
            "- Постановка автомобиля на учет\n"
            "- Продажа красивых номеров\n"
            "- Страхование"
        )

    elif text == "📞 Наш адрес и контакты":
        await update.message.reply_text(
            "🏢 Адрес: улица Твардовского, 8к5с1, Москва\n"
            "📍 [Открыть в Яндекс.Навигаторе](https://yandex.ru/navi/?ol=geo&text=%D1%83%D0%BB%D0%B8%D1%86%D0%B0%20%D0%A2%D0%B2%D0%B0%D1%80%D0%B4%D0%BE%D0%B2%D1%81%D0%BA%D0%BE%D0%B3%D0%BE,%208%D0%BA5%D1%811&sll=37.388268,55.792574)\n"
            "☎ [Позвонить: +7 (966) 000-26-26](tel:+79660002626)\n"
            "💬 Telegram: @blatznak77\n"
            "📱 [WhatsApp](https://wa.me/79660002626)",
            parse_mode="Markdown"
        )

    else:
        # Поиск по цифрам по умолчанию
        digits = text
        all_rows = get_all_numbers()
        results = []
        for row in all_rows:
            if not row or not row[0].strip():
                continue
            if digits in row[0]:
                line = format_row(row)
                if line:
                    results.append(line)
        if results:
            reply = "\n".join(results)
            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i:i+4000])
        else:
            await update.message.reply_text("❗ Номеров с такими цифрами не найдено.")

# === Main ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_handler))
    print("✅ Бот запущен. Polling активен...")
    app.run_polling()

if __name__ == "__main__":
    main()
