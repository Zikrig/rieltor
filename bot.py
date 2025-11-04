
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
 
from pathlib import Path
import re
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
 
import logging
from dotenv import load_dotenv

# --- Загрузка .env ---
load_dotenv()

# --- Настройка Google Sheets ---
SHEET_ID = os.getenv("SHEET_ID")
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "creds.json")
CREDS = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPES)
client = gspread.authorize(CREDS)
spreadsheet = client.open_by_key(SHEET_ID)
sheet = spreadsheet.sheet1

# --- Токен бота ---
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- Заголовки таблицы ---
HEADERS = ["Имя", "Бюджет", "Цель покупки", "Сроки", "Телефон"]

def ensure_sheet_headers() -> None:
    """Создаёт первую строку с заголовками, если она пустая."""
    try:
        first_row = sheet.row_values(1)
        if not first_row:
            sheet.update("A1:E1", [HEADERS])
    except Exception:
        # Тихо пропускаем, чтобы не ломать бота при временных ошибках сети
        pass

# (tgs import functionality removed)

# --- Машина состояний ---
 

# --- Простая анкета Юлии ---
class Survey(StatesGroup):
    name = State()
    budget = State()
    goal = State()
    timing = State()
    phone = State()

# --- Клавиатуры ---
 

# Клавиатуры анкеты (inline)
def make_budget_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10-20 млн руб", callback_data="budget:10-20 млн руб")],
        [InlineKeyboardButton(text="20-50 млн руб", callback_data="budget:20-50 млн руб")],
        [InlineKeyboardButton(text="50-80 млн руб", callback_data="budget:50-80 млн руб")],
        [InlineKeyboardButton(text="Более 100 млн руб", callback_data="budget:Более 100 млн руб")],
    ])

def make_goal_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перепродажа", callback_data="goal:Перепродажа")],
        [InlineKeyboardButton(text="Для сдачи/пассивного дохода", callback_data="goal:Для сдачи/пассивного дохода")],
        [InlineKeyboardButton(text="И то и другое", callback_data="goal:И то и другое")],
        [InlineKeyboardButton(text="Хотим свой дом у моря ❤️", callback_data="goal:Хотим свой дом у моря ❤️")],
    ])

def make_timing_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="В течение месяца", callback_data="timing:В течение месяца")],
        [InlineKeyboardButton(text="2-3 месяца", callback_data="timing:2-3 месяца")],
        [InlineKeyboardButton(text="4 и более месяца", callback_data="timing:4 и более месяца")],
    ])

 


# Новый приветственный текст для анкеты Юлии
INTRO_TEXT = (
    "Это Юлия 😃\n\n"
    "Ваш брокер по инвестициям в курортную недвижимость.\n\n"
    "Здесь вы найдете выгодные объекты с ростом цены и прозрачными условиями, а я помогу выбрать именно то, что подходит вам. 🌿\n\n"
    "Чтобы подобрать лучшие варианты, давайте начнем с трех вопросов о сроках, цели и бюджете покупки — это займет минуту и сразу покажет подходящие проекты.\n\n"
    "А потом можем встретиться на бесплатной консультации ☀️\n\n"
    "А как Вас зовут ?"
)

# --- Доп. тексты ---
CARE_TEXT = (
    "💬 <b>Служба заботы на связи</b>\n\n"
    "Напишите свой вопрос, и мы ответим вам в ближайшее время. "
    "Или сразу пишите <a href=\"https://t.me/dimafinesse\">@dimafinesse</a>."
)

 

# --- Нормализация и проверка телефона ---
def normalize_phone(raw: str) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    # keep plus for detection, strip others
    has_plus = text.startswith('+')
    digits = re.sub(r"\D", "", text)
    # Russian-specific normalizations
    if len(digits) == 11 and digits.startswith('8'):
        # 8XXXXXXXXXX -> +7XXXXXXXXXX
        return "+7" + digits[1:]
    if len(digits) == 11 and digits.startswith('7'):
        return "+7" + digits[1:]
    if len(digits) == 10:
        # Assume Russian local -> +7
        return "+7" + digits
    # If original had +, accept E.164 11-15 digits
    if has_plus and 11 <= len(digits) <= 15:
        return "+" + digits
    # Otherwise, reject
    return None

 

logging.basicConfig(level=logging.INFO)

# --- Обработчики ---
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    img_path = Path("data/image.png")
    if img_path.exists():
        try:
            await message.answer_photo(photo=FSInputFile(str(img_path)), caption=INTRO_TEXT)
        except Exception:
            await message.answer(INTRO_TEXT)
    else:
        await message.answer(INTRO_TEXT)
    await state.set_state(Survey.name)

async def survey_name(message: Message, state: FSMContext):
    user_name = message.text.strip()
    await state.update_data(name=user_name)
    greet_text = (
        f"Рада знакомству с Вами, {user_name}! \n\n"
        "Подскажите, пожалуйста, какой бюджет вы рассматриваете для покупки 💰 — это поможет сразу показать объекты с максимальной доходностью и комфортом."
    )
    await message.answer(greet_text, reply_markup=make_budget_kb())
    await state.set_state(Survey.budget)

async def on_budget_selected(cq: CallbackQuery, state: FSMContext):
    try:
        _, value = cq.data.split(":", 1)
    except Exception:
        await cq.answer()
        return
    await state.update_data(budget=value)
    await state.set_state(Survey.goal)
    await cq.message.edit_text(
        "Благодарю за ответ 🌿\n\nЕще важный вопрос — это цель покупки, от нее мы прокладываем стратегию.\n\nДля какой цели выбираете объекты?",
        reply_markup=make_goal_kb(),
    )
    await cq.answer()

async def on_goal_selected(cq: CallbackQuery, state: FSMContext):
    try:
        _, value = cq.data.split(":", 1)
    except Exception:
        await cq.answer()
        return
    await state.update_data(goal=value)
    await state.set_state(Survey.timing)
    await cq.message.edit_text(
        "На нашем рынке нередко появляются сильные предложения, и важно быть к ним готовыми ⚡️\n\nЧтобы я могла подобрать для вас лучшее — подскажите, пожалуйста, в какие сроки планируете покупку недвижимости?",
        reply_markup=make_timing_kb(),
    )
    await cq.answer()

async def on_timing_selected(cq: CallbackQuery, state: FSMContext):
    try:
        _, value = cq.data.split(":", 1)
    except Exception:
        await cq.answer()
        return
    await state.update_data(timing=value)
    await state.set_state(Survey.phone)
    await cq.message.edit_text(
        "Все мои клиенты 🥰 в числе первых, кто узнаёт о горячих предложениях.\n\nОставьте, пожалуйста, номер телефона в формате +7XXXXXXXXXX (можно 8XXXXXXXXXX) — и я буду держать вас в курсе 💪"
    )
    await cq.answer()

async def survey_phone(message: Message, state: FSMContext):
    raw_phone = (message.text or "").strip()
    normalized = normalize_phone(raw_phone)
    if not normalized:
        await message.answer("Пожалуйста, укажите номер телефона в формате +7XXXXXXXXXX (можно 8XXXXXXXXXX).")
        return

    await state.update_data(phone=normalized)
    data = await state.get_data()
    try:
        sheet.append_row([
            data.get("name", ""),
            data.get("budget", ""),
            data.get("goal", ""),
            data.get("timing", ""),
            data.get("phone", ""),
        ])
    except Exception:
        pass

    await message.answer(
        "✨ Спасибо за ваши ответы!\n\nТеперь я могу подобрать для вас лучшие объекты с прозрачными условиями и высоким потенциалом доходности.\n\n💌 Скоро свяжусь с Вами с персональными предложениями — будьте на связи!"
    )
    await state.clear()

 

 

# --- Запуск ---
async def main():
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Убедимся, что в таблице есть первая строка с заголовками
    ensure_sheet_headers()

    # Регистрация обработчиков только для простой анкеты
    dp.message.register(cmd_start, F.text == "/start")
    dp.message.register(survey_name, Survey.name)
    dp.callback_query.register(on_budget_selected, F.data.startswith("budget:"), Survey.budget)
    dp.callback_query.register(on_goal_selected, F.data.startswith("goal:"), Survey.goal)
    dp.callback_query.register(on_timing_selected, F.data.startswith("timing:"), Survey.timing)
    dp.message.register(survey_phone, Survey.phone)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
