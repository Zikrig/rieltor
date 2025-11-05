
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
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
HEADERS = ["Имя", "Логин", "Бюджет", "Цель покупки", "Сроки", "Телефон"]

def ensure_sheet_headers() -> None:
    """Создаёт или обновляет первую строку с заголовками."""
    try:
        first_row = sheet.row_values(1)
        if first_row != HEADERS:
            sheet.update("A1:F1", [HEADERS])
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

# --- Настройки PDF админом ---
class PdfSetup(StatesGroup):
    choose_goal = State()
    waiting_file = State()

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
    "Это <b>Юлия</b> 😃\n\n"
    "<b>Ваш брокер</b> по инвестициям в курортную недвижимость.\n\n"
    "Здесь вы найдете <b>выгодные объекты с ростом цены и прозрачными условиями</b>, а я помогу выбрать именно то, что подходит вам. 🌿\n\n"
    "Чтобы подобрать лучшие варианты, давайте начнем с трех вопросов о <b>сроках, цели и бюджете покупки</b> — это займет минуту и сразу покажет подходящие проекты.\n\n"
    "А потом можем встретиться на бесплатной консультации ☀️"
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

# --- Минимальная админ-подсистема (только для /pdf) ---
def _parse_admin_ids_from_env() -> set[int]:
    raw = os.getenv("ADMIN_IDS", "").replace(";", ",")
    ids: set[int] = set()
    for part in raw.split(','):
        p = part.strip()
        if p.isdigit():
            try:
                ids.add(int(p))
            except Exception:
                continue
    return ids

ADMIN_IDS = _parse_admin_ids_from_env()

def is_admin(user_id: int | None) -> bool:
    return bool(user_id and user_id in ADMIN_IDS)

# --- Конфиг PDF ---
PDF_CONFIG_PATH = Path("pdf_config.json")

# Список целей для admin UI и файловые слаги
PDF_GOAL_SLUGS: dict[str, str] = {
    "Перепродажа": "flip",
    "Для сдачи/пассивного дохода": "rent",
    "И то и другое": "both",
    "Хотим свой дом у моря ❤️": "house",
    "default": "default",
}

def load_pdf_mapping() -> dict:
    try:
        if PDF_CONFIG_PATH.exists():
            with open(PDF_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}

def save_pdf_mapping(mapping: dict) -> None:
    try:
        with open(PDF_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_pdf_path_for_goal(goal: str | None) -> Path:
    mapping = load_pdf_mapping()
    default_path = mapping.get("default", "data/test.pdf")
    if goal:
        path_str = mapping.get(goal, default_path)
    else:
        path_str = default_path
    return Path(path_str)

# --- Отложённое сохранение частичных данных ---
PENDING_SAVE_TASKS: dict[int, asyncio.Task] = {}

def _format_username(user) -> str:
    if user and getattr(user, "username", None):
        return f"@{user.username}"
    return ""

def cancel_partial_save(user_id: int) -> None:
    task = PENDING_SAVE_TASKS.pop(user_id, None)
    if task and not task.done():
        task.cancel()

def schedule_partial_save(user_id: int, state: FSMContext, bot: Bot) -> None:
    cancel_partial_save(user_id)
    PENDING_SAVE_TASKS[user_id] = asyncio.create_task(_partial_save_task(user_id, state, bot))

async def _partial_save_task(user_id: int, state: FSMContext, bot: Bot) -> None:
    try:
        await asyncio.sleep(60)
        data = await state.get_data()
        if not data:
            return
        row = [
            data.get("name", ""),
            data.get("username", ""),
            data.get("budget", ""),
            data.get("goal", ""),
            data.get("timing", ""),
            data.get("phone", ""),
        ]
        try:
            sheet.append_row(row)
        except Exception:
            pass
        # Уведомляем админов об незавершённой анкете
        try:
            summary = (
                "Незавершенная анкета (таймаут 60с):\n"
                f"Имя: {data.get('name','')}\n"
                f"Логин: {data.get('username','')}\n"
                f"Бюджет: {data.get('budget','')}\n"
                f"Цель: {data.get('goal','')}\n"
                f"Сроки: {data.get('timing','')}\n"
                f"Телефон: {data.get('phone','')}"
            )
            await notify_admins(bot, summary)
        except Exception:
            pass
    except asyncio.CancelledError:
        return

async def notify_admins(bot: Bot, text: str) -> None:
    if not ADMIN_IDS:
        return
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            continue

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
    # Отдельным сообщением спрашиваем имя
    await message.answer("Напишите, пожалуйста, Ваше имя")
    # Сохраняем логин пользователя для таблицы
    await state.update_data(username=_format_username(message.from_user))
    # Планируем отложенное сохранение частичных данных
    if message.from_user and message.from_user.id:
        schedule_partial_save(message.from_user.id, state, message.bot)
    await state.set_state(Survey.name)

def make_pdf_goals_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=k, callback_data=f"pdfgoal:{k}")] for k in PDF_GOAL_SLUGS.keys()
    ])

async def admin_pdf_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    mapping = load_pdf_mapping()
    current = json.dumps(mapping, ensure_ascii=False, indent=2) if mapping else "(пока не задано, по умолчанию data/test.pdf)"
    await state.set_state(PdfSetup.choose_goal)
    await message.answer("Выберите цель, для которой хотите загрузить новый PDF.\n\nТекущие значения:\n" + current, reply_markup=make_pdf_goals_kb())

def _parse_pdf_mapping_lines(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=" in line:
            key, val = line.split("=", 1)
        elif ":" in line:
            key, val = line.split(":", 1)
        else:
            continue
        key = key.strip()
        val = val.strip()
        if key and val:
            result[key] = val
    return result

async def on_pdf_goal_selected(cq: CallbackQuery, state: FSMContext):
    if not is_admin(cq.from_user.id):
        await cq.answer()
        return
    try:
        _, goal = cq.data.split(":", 1)
    except Exception:
        await cq.answer()
        return
    await state.update_data(pdf_goal=goal)
    await state.set_state(PdfSetup.waiting_file)
    await cq.message.edit_text(f"Цель: {goal}\n\nПришлите PDF-файл (документ) для этой цели. Прежний файл будет заменён.")
    await cq.answer()

async def admin_pdf_receive_document(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    data = await state.get_data()
    goal = data.get("pdf_goal")
    if not goal:
        await message.answer("Сначала выберите цель через /pdf.")
        await state.clear()
        return
    if not getattr(message, "document", None):
        await message.answer("Пожалуйста, пришлите PDF-файл как документ.")
        return
    # Проверим тип
    mime = getattr(message.document, "mime_type", "") or ""
    if "pdf" not in mime.lower():
        await message.answer("Это не похоже на PDF. Пришлите документ с типом PDF.")
        return
    # Определим путь сохранения
    slug = PDF_GOAL_SLUGS.get(goal, "custom")
    Path("data").mkdir(parents=True, exist_ok=True)
    dest_path = Path(f"data/pdf_{slug}.pdf")
    try:
        await message.bot.download(file=message.document, destination=dest_path)
        mapping = load_pdf_mapping()
        mapping[goal] = str(dest_path)
        save_pdf_mapping(mapping)
        await message.answer(f"Файл сохранён для цели '{goal}': {dest_path}\nГотово.")
    except Exception:
        await message.answer("Не удалось сохранить файл. Попробуйте позже.")
    finally:
        await state.clear()

async def survey_name(message: Message, state: FSMContext):
    user_name = message.text.strip()
    await state.update_data(name=user_name)
    greet_text = (
        f"Рада знакомству с Вами, {user_name}! \n\n"
        "Подскажите, пожалуйста, какой бюджет вы рассматриваете для покупки 💰 — это поможет сразу показать объекты с максимальной доходностью и комфортом."
    )
    await message.answer(greet_text, reply_markup=make_budget_kb())
    # Перепланируем отложенное сохранение
    if message.from_user and message.from_user.id:
        schedule_partial_save(message.from_user.id, state, message.bot)
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
    # Перепланируем отложенное сохранение
    schedule_partial_save(cq.from_user.id, state, cq.message.bot)
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
    # Перепланируем отложенное сохранение
    schedule_partial_save(cq.from_user.id, state, cq.message.bot)
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
    # Перепланируем отложенное сохранение
    schedule_partial_save(cq.from_user.id, state, cq.message.bot)
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
            data.get("username", ""),
            data.get("budget", ""),
            data.get("goal", ""),
            data.get("timing", ""),
            data.get("phone", ""),
        ])
    except Exception:
        pass

    # Уведомление админам о завершении анкеты
    try:
        summary = (
            "Новая анкета:\n"
            f"Имя: {data.get('name','')}\n"
            f"Логин: {data.get('username','')}\n"
            f"Бюджет: {data.get('budget','')}\n"
            f"Цель: {data.get('goal','')}\n"
            f"Сроки: {data.get('timing','')}\n"
            f"Телефон: {data.get('phone','')}"
        )
        await notify_admins(message.bot, summary)
    except Exception:
        pass

    await message.answer(
            "Спасибо за ответы! 🙏\n\n"
            "Подписывайтесь на мой <a href=\"https://t.me/Broker_9Avenu\">КАНАЛ</a> и будете в курсе новостей и рынка ☝️\n\n"
            "💌 Задать вопрос лично можно <a href=\"https://t.me/uu_promore\">здесь</a>\n\n"
            "Я уже подготовила для вас персонализированную презентацию с лучшими предложениями.\n\n"
            "📎 Скачивайте презентацию и изучайте предложения!"
    )
    # Отправляем PDF следующим сообщением, исходя из выбранной цели
    goal_value = data.get("goal")
    pdf_path = get_pdf_path_for_goal(goal_value)
    try:
        if not pdf_path.exists():
            # Фоллбэк к дефолтному, если указанного файла нет
            fallback = Path("data/test.pdf")
            if fallback.exists():
                pdf_path = fallback
        if pdf_path.exists():
            await message.answer_document(document=FSInputFile(str(pdf_path)))
    except Exception:
        pass
    # Отменяем отложенное сохранение, анкета завершена
    if message.from_user and message.from_user.id:
        cancel_partial_save(message.from_user.id)
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
    # Админ: настройка PDF по целям
    dp.message.register(admin_pdf_start, F.text == "/pdf")
    dp.callback_query.register(on_pdf_goal_selected, F.data.startswith("pdfgoal:"), PdfSetup.choose_goal)
    dp.message.register(admin_pdf_receive_document, PdfSetup.waiting_file)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
