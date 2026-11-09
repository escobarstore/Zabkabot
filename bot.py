import json
import logging
import os
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

TOKEN = os.environ["BOT_TOKEN"]
SHOP_NAME = os.getenv("SHOP_NAME", "Mój sklep")
CURRENCY = os.getenv("CURRENCY", "PLN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip().lstrip("@")

ROOT = Path(__file__).resolve().parent
PRODUCTS_PATH = ROOT / "products.json"

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def load_products():
    with PRODUCTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def product_by_id(pid):
    return next((p for p in load_products() if str(p["id"]) == str(pid)), None)


def unit_price(product, quantity):
    """Use the best matching quantity tier; tiers are minimum quantities."""
    price = float(product["price"])
    for tier in sorted(product.get("price_tiers", []), key=lambda x: int(x["min_qty"])):
        if quantity >= int(tier["min_qty"]):
            price = float(tier["unit_price"])
    return price


def money(value):
    return f"{value:.2f} {CURRENCY}"


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ Otwórz katalog", callback_data="catalog")]
    ])


def catalog_markup():
    rows = []
    for p in load_products():
        rows.append([InlineKeyboardButton(
            f'{p["name"]} — od {money(float(p["price"]))}/szt.',
            callback_data=f'product:{p["id"]}'
        )])
    rows.append([InlineKeyboardButton("🧺 Mój koszyk", callback_data="cart")])
    return Inlineline(rows)


def Inlineline(rows):
    return InlineKeyboardMarkup(rows)


def product_markup(product, qty):
    pid = product["id"]
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data=f"qty:{pid}:{max(1, qty-1)}"),
            InlineKeyboardButton(f"Ilość: {qty}", callback_data="noop"),
            InlineKeyboardButton("➕", callback_data=f"qty:{pid}:{qty+1}"),
        ],
        [InlineKeyboardButton(
            f"Dodaj do koszyka · {money(unit_price(product, qty) * qty)}",
            callback_data=f"add:{pid}:{qty}"
        )],
        [InlineKeyboardButton("⬅️ Katalog", callback_data="catalog"),
         InlineKeyboardButton("🧺 Koszyk", callback_data="cart")],
    ])


def cart_text(cart):
    if not cart:
        return "Twój koszyk jest pusty."
    lines = ["🧺 **Twój koszyk**", ""]
    total = 0.0
    for pid, qty in cart.items():
        p = product_by_id(pid)
        if not p:
            continue
        price = unit_price(p, qty)
        subtotal = price * qty
        total += subtotal
        lines.append(f'• {p["name"]} — {qty} szt. × {money(price)} = {money(subtotal)}')
    lines += ["", f"**Razem: {money(total)}**"]
    return "\n".join(lines)


def cart_markup(cart):
    rows = []
    for pid, qty in cart.items():
        p = product_by_id(pid)
        if p:
            rows.append([
                InlineKeyboardButton(f'➖ {p["name"]}', callback_data=f"cartdec:{pid}"),
                InlineKeyboardButton(f"{qty} szt.", callback_data="noop"),
                InlineKeyboardButton("➕", callback_data=f"cartinc:{pid}"),
                InlineKeyboardButton("✖️", callback_data=f"cartremove:{pid}"),
            ])
    rows.extend([
        [InlineKeyboardButton("➕ Dodaj kolejny produkt", callback_data="catalog")],
        [InlineKeyboardButton("Przejdź dalej", callback_data="checkout")],
        [InlineKeyboardButton("Wyczyść koszyk", callback_data="cartclear")],
    ])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("cart", {})
    await update.message.reply_text(
        f"Witaj w {SHOP_NAME}!\nZobacz katalog produktów i dodaj wybrane pozycje do koszyka.",
        reply_markup=main_menu(),
    )


async def show_product(query, context, pid, qty=None):
    p = product_by_id(pid)
    if not p:
        await query.message.reply_text("Nie znaleziono tego produktu.")
        return
    if qty is None:
        qty = context.user_data.setdefault("product_qty", {}).get(str(pid), 1)
    qty = max(1, min(int(qty), 99))
    context.user_data.setdefault("product_qty", {})[str(pid)] = qty

    tiers = p.get("price_tiers", [])
    tier_text = ""
    if tiers:
        tier_lines = [f'{t["min_qty"]}+ szt. — {money(float(t["unit_price"]))}/szt.' for t in tiers]
        tier_text = "\n\nCennik ilościowy:\n" + "\n".join(tier_lines)

    text = (
        f'**{p["name"]}**\n\n{p.get("description", "")}\n\n'
        f'Cena dla {qty} szt.: {money(unit_price(p, qty))}/szt. '
        f'(razem {money(unit_price(p, qty) * qty)}){tier_text}'
    )
    markup = product_markup(p, qty)
    image_name = p.get("image", "")
    image_path = (ROOT / image_name).resolve() if image_name else None
    if image_path and ROOT.resolve() in image_path.parents and image_path.is_file():
        with image_path.open("rb") as photo:
            await query.message.reply_photo(
                photo=photo, caption=text, parse_mode="Markdown", reply_markup=markup
            )
    else:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    cart = context.user_data.setdefault("cart", {})

    if data == "noop":
        return
    if data == "catalog":
        await q.message.reply_text("Wybierz produkt:", reply_markup=catalog_markup())
    elif data.startswith("product:"):
        await show_product(q, context, data.split(":")[1])
    elif data.startswith("qty:"):
        _, pid, qty = data.split(":")
        await show_product(q, context, pid, int(qty))
    elif data.startswith("add:"):
        _, pid, qty = data.split(":")
        cart[pid] = cart.get(pid, 0) + int(qty)
        p = product_by_id(pid)
        await q.message.reply_text(
            f'Dodano do koszyka: {p["name"]} — {qty} szt.',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧺 Zobacz koszyk", callback_data="cart")],
                [InlineKeyboardButton("Kontynuuj zakupy", callback_data="catalog")],
            ])
        )
    elif data == "cart":
        await q.message.reply_text(
            cart_text(cart), parse_mode="Markdown", reply_markup=cart_markup(cart)
        )
    elif data.startswith("cartinc:"):
        pid = data.split(":")[1]
        cart[pid] = cart.get(pid, 0) + 1
        await q.message.reply_text(cart_text(cart), parse_mode="Markdown", reply_markup=cart_markup(cart))
    elif data.startswith("cartdec:"):
        pid = data.split(":")[1]
        cart[pid] = max(0, cart.get(pid, 0) - 1)
        if cart[pid] == 0:
            cart.pop(pid, None)
        await q.message.reply_text(cart_text(cart), parse_mode="Markdown", reply_markup=cart_markup(cart))
    elif data.startswith("cartremove:"):
        cart.pop(data.split(":")[1], None)
        await q.message.reply_text(cart_text(cart), parse_mode="Markdown", reply_markup=cart_markup(cart))
    elif data == "cartclear":
        cart.clear()
        await q.message.reply_text("Koszyk został wyczyszczony.", reply_markup=main_menu())
    elif data == "checkout":
        if not cart:
            await q.message.reply_text("Koszyk jest pusty. Najpierw wybierz produkt.")
            return
        summary = cart_text(cart)
        if ADMIN_USERNAME:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("Skontaktuj się z administratorem", url=f"https://t.me/{ADMIN_USERNAME}")
            ]])
            await q.message.reply_text(
                summary + "\n\nTo jest podsumowanie katalogowe, nie potwierdzenie płatności ani zamówienia. "
                "Aby uzgodnić dalsze kroki, skontaktuj się z administratorem.",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            await q.message.reply_text(
                summary + "\n\nUstaw ADMIN_USERNAME w Railway, aby dodać przycisk kontaktu.",
                parse_mode="Markdown",
            )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Wpisz /start, aby otworzyć katalog.")


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(callback))
    log.info("Starting catalogue bot")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
