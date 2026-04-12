# -*- coding: utf-8 -*-
import os
import logging
import re
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"

# === Google Sheets ===
SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
CREDS = ServiceAccountCredentials.from_json_keyfile_name(
    "blat-znak-63d9713dc5ce.json", SCOPES
)
gc = gspread.authorize(CREDS)
SPREADSHEET = gc.open("все_номера_для_бота")

# Все листы с номерами (поиск ведётся по всем)
ALL_SHEETS = ["Москва", "Московская область", "Мото", "Мото МО", "Прицеп"]

# Кэш листов
_sheet_cache = {}

def get_sheet(name: str):
    if name not in _sheet_cache:
        _sheet_cache[name] = SPREADSHEET.worksheet(name)
    return _sheet_cache[name]

def get_rows(sheet_name: str):
    """Возвращает все строки листа без заголовка."""
    ws = get_sheet(sheet_name)
    return ws.get_all_values()[1:]

# === Транслитерация ===
def ru_to_lat(text: str) -> str:
    repl = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")
    return text.translate(repl)

# === Форматирование цены ===
def format_price(price_str: str) -> str:
    """
    Если цена — чистое число (без точек/пробелов), добавляем точки каждые 3 цифры.
    Если уже есть точки — оставляем как есть.
    """
    p = price_str.strip()
    if re.fullmatch(r"\d+", p):
        return f"{int(p):,}".replace(",", ".")
    return p

# === Форматирование строки номера ===
def format_row(row) -> str:
    """row = [Номер, Цена, Примечание] — для новых листов (Москва, Мото, Прицеп...)"""
    number = row[0] if len(row) > 0 else ""
    price  = format_price(row[1]) if len(row) > 1 else ""
    note   = row[2] if len(row) > 2 else ""
    line = f"{number} — {price}₽"
    if note.strip():
        line += f" {note.strip()}"
    return line


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

# === Отправка листа с пагинацией ===
async def send_sheet_paginated(update: Update, sheet_name: str, page_size: int):
    rows = get_rows(sheet_name)
    if not rows:
        await update.message.reply_text("Список пуст.")
        return
    lines = [format_row(r) for r in rows if r and r[0].strip()]
    for i in range(0, len(lines), page_size):
        chunk = "\n".join(lines[i:i + page_size])
        await update.message.reply_text(chunk)

# === Поиск по всем листам ===
def search_by_digits(digits: str):
    results = []
    for sheet_name in ALL_SHEETS:
        for row in get_rows(sheet_name):
            if row and digits in row[0]:
                results.append(f"[{sheet_name}] {format_row(row)}")
    return results

def search_by_letters(query_lat: str):
    results = []
    for sheet_name in ALL_SHEETS:
        for row in get_rows(sheet_name):
            if not row or not row[0].strip():
                continue
            only_letters = ru_to_lat("".join(re.findall(r"[А-ЯA-Z]+", row[0].upper())))
            if query_lat in only_letters:
                results.append(f"[{sheet_name}] {format_row(row)}")
    return results

async def send_results(update, results):
    if results:
        reply = "\n".join(results)
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i:i+4000])
    else:
        await update.message.reply_text("❗ Ничего не найдено.")

# === Универсальный обработчик ===
async def unified_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_data = context.user_data

    # --- Старт ---
    if text == "🔁 Старт":
        await start(update, context)
        return

    # --- Ожидаем размер страницы ---
    if user_data.get("expecting_page_size"):
        try:
            page_size = int(text)
            if page_size < 1 or page_size > 200:
                raise ValueError
            user_data["expecting_page_size"] = False
            await send_sheet_paginated(update, user_data["selected_sheet"], page_size)
        except ValueError:
            user_data["expecting_page_size"] = False
            await update.message.reply_text(
                "❗ Ожидалось число от 1 до 200. Попробуйте ещё раз или нажмите 🔁 Старт."
            )
        return

    # --- Поиск по буквам ---
    if text == "🔠 Поиск номера по буквам":
        user_data["expecting_letter_search"] = True
        await update.message.reply_text("Введите буквы для поиска (например, МК или АА):")
        return

    if user_data.get("expecting_letter_search"):
        query = ru_to_lat(text.upper())
        user_data["expecting_letter_search"] = False
        results = search_by_letters(query)
        await send_results(update, results)
        return

    # --- Поиск по цифрам (кнопка) ---
    if text == "🔍 Поиск номера по цифрам":
        user_data["expecting_digit_search"] = True
        await update.message.reply_text("Отправьте цифры для поиска (например, 777):")
        return

    if user_data.get("expecting_digit_search"):
        user_data["expecting_digit_search"] = False
        results = search_by_digits(text.strip())
        await send_results(update, results)
        return

    # --- Мото номера ---
    if text == "🛵 Мото номера":
        user_data["expecting_page_size"] = True
        user_data["selected_sheet"] = "Мото"
        await update.message.reply_text("Сколько номеров показать на странице? (например, 30, максимум 200)")
        return

    # --- Прицеп номера ---
    if text == "🚛 Прицеп номера":
        user_data["expecting_page_size"] = True
        user_data["selected_sheet"] = "Прицеп"
        await update.message.reply_text("Сколько номеров показать на странице? (например, 30, максимум 200)")
        return

    # --- Москва все номера ---
    if text == "📍 Москва все номера":
        user_data["expecting_page_size"] = True
        user_data["selected_sheet"] = "Москва"
        await update.message.reply_text("Сколько номеров показать на странице? (например, 30, максимум 200)")
        return

    # --- Московская область ---
    if text == "📍 Московская обл. все номера":
        user_data["expecting_page_size"] = True
        user_data["selected_sheet"] = "Московская область"
        await update.message.reply_text("Сколько номеров показать на странице? (например, 30, максимум 200)")
        return

    # --- Услуги ---
    if text == "🛠 Наши услуги":
        await update.message.reply_text(
            "📌 Наши услуги:\n"
            "- Дубликат номеров\n"
            "- Постановка автомобиля на учет\n"
            "- Продажа красивых номеров\n"
            "- Страхование"
        )
        return

    # --- Контакты ---
    if text == "📞 Наш адрес и контакты":
        await update.message.reply_text(
            "🏢 Адрес: улица Твардовского, 8к5с1, Москва\n"
            "📍 [Открыть в Яндекс.Навигаторе](https://yandex.ru/navi/?ol=geo&text=%D1%83%D0%BB%D0%B8%D1%86%D0%B0%20%D0%A2%D0%B2%D0%B0%D1%80%D0%B4%D0%BE%D0%B2%D1%81%D0%BA%D0%BE%D0%B3%D0%BE,%208%D0%BA5%D1%811&sll=37.388268,55.792574)\n"
            "☎ [Позвонить: +7 (966) 000-26-26](tel:+79660002626)\n"
            "💬 Telegram: @blatznak77\n"
            "📱 [WhatsApp](https://wa.me/79660002626)",
            parse_mode="Markdown"
        )
        return

    # --- Поиск по цифрам (прямой ввод цифр без кнопки) ---
    if re.fullmatch(r"\d+", text):
        results = search_by_digits(text)
        await send_results(update, results)
        return

    # --- Неизвестный ввод ---
    await update.message.reply_text(
        "Не понял запрос. Воспользуйтесь кнопками меню или нажмите 🔁 Старт."
    )

# === Main ===
def main():
    # Прокси для обхода блокировки Telegram в России
    proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or None
    builder = Application.builder().token(BOT_TOKEN)
    if proxy_url:
        request = HTTPXRequest(proxy=proxy_url)
        builder = builder.request(request)
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_handler))
    print("✅ Бот запущен. Polling активен...")
    app.run_polling()

if __name__ == "__main__":
    main()
