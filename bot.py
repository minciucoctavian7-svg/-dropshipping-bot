
import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
DB = "oto_market.db"

PRODUCTS = [
    {"id": 1, "name": "Товар 1", "price": 0, "description": "Добавьте товар через PRODUCTS в bot.py"},
]

def db():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT, phone TEXT, address TEXT,
        product_id INTEGER, product_name TEXT, price REAL,
        created_at TEXT
    )""")
    return conn

def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Каталог", callback_data="catalog")],
        [InlineKeyboardButton("🔥 Акции", callback_data="promo")],
        [InlineKeyboardButton("💬 Задать вопрос", callback_data="question")],
        [InlineKeyboardButton("📦 Мои заказы", callback_data="orders")],
    ])

def product_keyboard(p):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Заказать", callback_data=f"buy:{p['id']}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="catalog")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать в OTO Market! 🛍\n\n"
        "Выберите действие:",
        reply_markup=menu()
    )

async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "catalog":
        rows = [[InlineKeyboardButton(
            f"{p['name']} — {p['price']} €", callback_data=f"product:{p['id']}"
        )] for p in PRODUCTS]
        rows.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="home")])
        await q.edit_message_text("🛍 Каталог:", reply_markup=InlineKeyboardMarkup(rows))

    elif q.data == "home":
        await q.edit_message_text("Главное меню:", reply_markup=menu())

    elif q.data == "promo":
        await q.edit_message_text(
            "🔥 Акции пока настраиваются.\n"
            "Здесь позже можно автоматически показывать товары со скидкой.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data="home")]]
            )
        )

    elif q.data == "question":
        context.user_data["awaiting_question"] = True
        await q.edit_message_text("💬 Напишите ваш вопрос одним сообщением.")

    elif q.data == "orders":
        conn = db()
        rows = conn.execute(
            "SELECT id, product_name, price, created_at FROM orders "
            "WHERE user_id=? ORDER BY id DESC LIMIT 10", (q.from_user.id,)
        ).fetchall()
        conn.close()
        if not rows:
            text = "📦 У вас пока нет заказов."
        else:
            text = "📦 Ваши заказы:\n\n" + "\n".join(
                f"№{r[0]} — {r[1]} — {r[2]} €\n{r[3]}" for r in rows
            )
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Главное меню", callback_data="home")]]
        ))

    elif q.data.startswith("product:"):
        pid = int(q.data.split(":")[1])
        p = next((x for x in PRODUCTS if x["id"] == pid), None)
        if not p:
            await q.edit_message_text("Товар не найден.")
            return
        await q.edit_message_text(
            f"🛍 {p['name']}\n\n{p['description']}\n\n💶 Цена: {p['price']} €",
            reply_markup=product_keyboard(p)
        )

    elif q.data.startswith("buy:"):
        pid = int(q.data.split(":")[1])
        p = next((x for x in PRODUCTS if x["id"] == pid), None)
        context.user_data["order_product"] = p
        context.user_data["order_step"] = "name"
        await q.edit_message_text("📝 Как вас зовут?")

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if context.user_data.get("awaiting_question"):
        context.user_data["awaiting_question"] = False
        if ADMIN_CHAT_ID:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"💬 Вопрос от @{update.effective_user.username or update.effective_user.id}:\n{text}"
            )
        await update.message.reply_text(
            "Спасибо! Вопрос передан менеджеру. Мы свяжемся с вами.",
            reply_markup=menu()
        )
        return

    step = context.user_data.get("order_step")
    if step == "name":
        context.user_data["order_name"] = text
        context.user_data["order_step"] = "phone"
        await update.message.reply_text("📱 Напишите номер телефона.")
    elif step == "phone":
        context.user_data["order_phone"] = text
        context.user_data["order_step"] = "address"
        await update.message.reply_text("📍 Напишите адрес доставки.")
    elif step == "address":
        p = context.user_data["order_product"]
        name = context.user_data["order_name"]
        phone = context.user_data["order_phone"]
        address = text
        conn = db()
        cur = conn.execute(
            """INSERT INTO orders
            (user_id,name,phone,address,product_id,product_name,price,created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (update.effective_user.id, name, phone, address,
             p["id"], p["name"], p["price"], datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        order_id = cur.lastrowid
        conn.commit()
        conn.close()

        if ADMIN_CHAT_ID:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"🛒 НОВЫЙ ЗАКАЗ №{order_id}\n"
                    f"Товар: {p['name']}\n"
                    f"Цена: {p['price']} €\n"
                    f"Имя: {name}\nТелефон: {phone}\nАдрес: {address}"
                )
            )

        context.user_data.clear()
        await update.message.reply_text(
            f"✅ Заказ №{order_id} принят!\n"
            "Менеджер свяжется с вами для подтверждения.",
            reply_markup=menu()
        )
    else:
        await update.message.reply_text(
            "Выберите действие в меню 👇",
            reply_markup=menu()
        )

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OTO Market Bot is running")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server listening on port {port}.")
    server.serve_forever()


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не задан")

    # Render Web Service expects the process to listen on PORT.
    threading.Thread(target=start_health_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    print("OTO Market запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
