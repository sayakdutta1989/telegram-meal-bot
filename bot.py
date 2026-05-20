import os
import json
import random
import asyncio
from datetime import datetime, timedelta
from threading import Thread

from flask import Flask

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_URL")

TRIGGER = "hi"

HISTORY_FILE = "history.json"

# cooldown before repeating meals
COOLDOWN_DAYS = {
    "breakfast": 2,
    "lunch": 3,
    "dinner": 2
}

# auto-delete history older than this
HISTORY_RETENTION_DAYS = 14

# =========================
# FLASK APP
# =========================

app_web = Flask(__name__)

# =========================
# LOAD MENU
# =========================

with open("menu.json", "r") as f:
    MENU = json.load(f)

# =========================
# HISTORY HELPERS
# =========================

def load_history():

    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)

    except:
        return {}


def save_history(history):

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def cleanup_old_history(history):

    today = datetime.now().date()

    cleaned_history = {}

    for category, meals in history.items():

        cleaned_history[category] = {}

        for item, date_str in meals.items():

            try:

                last_date = datetime.strptime(
                    date_str,
                    "%Y-%m-%d"
                ).date()

                age = (today - last_date).days

                if age <= HISTORY_RETENTION_DAYS:

                    cleaned_history[category][item] = date_str

            except:
                pass

    return cleaned_history


# =========================
# SMART RANDOM SELECTION
# =========================

def choose_meal(category, options, history):

    today = datetime.now().date()

    valid_options = []

    for item in options:

        last_used = history.get(category, {}).get(item)

        # never used before
        if not last_used:
            valid_options.append(item)
            continue

        last_date = datetime.strptime(
            last_used,
            "%Y-%m-%d"
        ).date()

        days_gap = (today - last_date).days

        cooldown = COOLDOWN_DAYS[category]

        # enough cooldown gap passed
        if days_gap >= cooldown:
            valid_options.append(item)

    # fallback if everything blocked
    if not valid_options:
        valid_options = options

    selected = random.choice(valid_options)

    # update history
    history.setdefault(category, {})
    history[category][selected] = str(today)

    return selected


# =========================
# MAIN BOT LOGIC
# =========================

async def reply_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    message = update.message.text.lower().strip()

    if message != TRIGGER:
        return

    today = datetime.now().strftime("%A").lower()

    if today not in MENU:

        await update.message.reply_text(
            "No menu configured for today."
        )

        return

    # load + cleanup history
    history = load_history()

    history = cleanup_old_history(history)

    breakfast = choose_meal(
        "breakfast",
        MENU[today]["breakfast"],
        history
    )

    lunch = choose_meal(
        "lunch",
        MENU[today]["lunch"],
        history
    )

    dinner = choose_meal(
        "dinner",
        MENU[today]["dinner"],
        history
    )

    # save updated history
    save_history(history)

    response = f"""
Today's menu 🍽️

Breakfast: {breakfast}
Lunch: {lunch}
Dinner: {dinner}
"""

    await update.message.reply_text(response)


# =========================
# TELEGRAM APPLICATION
# =========================

telegram_app = Application.builder().token(BOT_TOKEN).build()

telegram_app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        reply_menu
    )
)

# =========================
# FLASK ROUTES
# =========================

@flask_app.route("/")
def home():
    return "Bot is live"

@flask_app.route("/webhook", methods=["POST"])
async def webhook():

    data = request.get_json()

    update = Update.de_json(
        data,
        telegram_app.bot
    )

    await telegram_app.process_update(update)

    return "ok"

# =========================
# STARTUP
# =========================

async def setup_webhook():

    webhook_url = f"{RENDER_URL}/webhook"

    await telegram_app.bot.set_webhook(webhook_url)

    print(f"Webhook set to: {webhook_url}")

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    import asyncio

    loop = asyncio.get_event_loop()

    loop.run_until_complete(
        telegram_app.initialize()
    )

    loop.run_until_complete(
        setup_webhook()
    )

    print("Webhook bot started successfully...")

    port = int(os.environ.get("PORT", 10000))

    flask_app.run(
        host="0.0.0.0",
        port=port
    )
