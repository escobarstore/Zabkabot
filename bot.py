import os
from pathlib import Path
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip().lstrip("@")
PRODUCTS_FILE = Path(__file__).with_name("products.json")
IMAGE_DIR = Path(__file__).with_name("images")


def load_products():
    if not PRODUCTS_FILE.exists():
        raise FileNotFoundError("Brak pliku products.json obok bot.py")
    data = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("products.json musi zawierać listę produktów")
    for i, product in enumerate(data):
        product.setdefault("id", str(i + 1))
        product.setdefault("name", f"Produkt {i + 1}")
        product.setdefault("price", 0)
        product.setdefault("description", "")
        product.setdefault("image", "")
        product.setdefault("price_tiers", [])
    return data


PRODUCTS = load_products()
PRODUCT_BY_ID = {str(p["id"]): p for p in PRODUCTS}


def unit_price(product, quantity):
    """Zwraca cenę jednostkową dla ilości danego produktu."""
    price = float(product.get("price", 0))
    tiers = sorted(
        product.get("price_tiers", []),
        key=lambda item: int(item.get("min_qty", 1))
    )
    for tier in tiers:
        if quantity >= int(tier.get("min_qty", 1)):
            price = float(tier.get("unit_price", price))
    return price


def money(value):
    return f"{value:.2f}".replace(".", ",") + " zł"


def product_text(product, quantity):
    price = unit_price(product, quantity)
    total = price * quantity
    lines = [
        f"<b>{product['name']}</b>",
        "",
        product.get("description", ""),
        "",
        f"Cena za sztukę: <b>{money(price)}</b>",
        f"Ilość: <b>{quantity}</b>",
        f"Wartość: <b>{money(total)}</b>",
    ]
    return "\n".join(line for line in lines if line is not None)


def catalog_keyboard():
    rows = []
    for product in PRODUCTS:
        rows.append([InlineKeyboardButton(
            str(product["name"])[:60],
            callback_data=f"product:{product['id']}"
        )])
    rows.append([InlineKeyboardButton("🛒 Koszyk", callback_data="cart")])
    return InlineKeyboardMarkup(rows)


def product_keyboard(product_id, quantity):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("−", callback_data=f"qty:{product_id}:{max(1, quantity-1)}"),
            InlineKeyboardButton(str(quantity), callback_data="noop"),
            InlineKeyboardButton("+", callback_data=f"qty:{product_id}:{min(999, quantity+1)}"),
        ],
        [InlineKeyboardButton("🛒 Dodaj do koszyka", callback_data=f"add:{product_id}:{quantity}")],
        [InlineKeyboardButton("⬅️ Wróć do katalogu", callback_data="catalog")],
        [InlineKeyboardButton("🛒 Zobacz koszyk", callback_data="cart")],
    ])


def cart_keyboard(cart):
    rows = []
    for product_id, quantity in cart.items():
        product = PRODUCT_BY_ID.get(str(product_id))
        if product:
            rows.append([InlineKeyboardButton(
                f"✏️ {product['name'][:32]} ({quantity} szt.)",
                callback_data=f"product:{product_id}"
            )])
    rows.extend([
        [InlineKeyboardButton("🧹 Wyczyść koszyk", callback_data="clear_cart")],
        [InlineKeyboardButton("⬅️ Katalog", callback_data="catalog")],
    ])
    if ADMIN_USERNAME:
        rows.append([InlineKeyboardButton(
            "Kontakt z administratorem",
            url=f"https://t.me/{ADMIN_USERNAME}"
        )])
    return InlineKeyboardMarkup(rows)


def cart_text(cart):
    if not cart:
        return "<b>Twój koszyk jest pusty.</b>"
    lines = ["<b>🛒 Twój koszyk</b>", ""]
    total = 0.0
    for product_id, quantity in cart.items():
        product = PRODUCT_BY_ID.get(str(product_id))
        if not product:
            continue
        price = unit_price(product, quantity)
        subtotal = price * quantity
        total += subtotal
        lines.append(
            f"• {product['name']} — {quantity} × {money(price)} = <b>{money(subtotal)}</b>"
        )
    lines.extend(["", f"<b>Razem: {money(total)}</b>"])
    return "\n".join(lines)


async def show_catalog(query):
    await query.edit_message_text(
        "<b>Wybierz produkt z katalogu:</b>",
        reply_markup=catalog_keyboard(),
        parse_mode="HTML"
    )


async def show_product(query, context, product_id, quantity=None):
    product = PRODUCT_BY_ID.get(str(product_id))
    if not product:
        await query.answer("Nie znaleziono produktu.", show_alert=True)
        return

    if quantity is None:
        quantity = int(context.user_data.get(f"qty_{product_id}", 1))
    quantity = max(1, min(999, int(quantity)))
    context.user_data[f"qty_{product_id}"] = quantity

    text = product_text(product, quantity)
    keyboard = product_keyboard(product_id, quantity)
    image_value = str(product.get("image", "")).strip()
    image_path = IMAGE_DIR / image_value if image_value else None
    has_image = bool(image_path and image_path.is_file())

    message = query.message
    is_photo = bool(message.photo)

    try:
        if has_image:
            if is_photo:
                with image_path.open("rb") as photo:
                    await query.edit_message_media(
                        media=InputMediaPhoto(
                            media=photo, caption=text, parse_mode="HTML"
                        ),
                        reply_markup=keyboard
                    )
            else:
                # Gdy poprzednia wiadomość była tekstowa, usuń ją i wyślij kartę ze zdjęciem.
                await message.delete()
                with image_path.open("rb") as photo:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id,
                        photo=photo,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
        else:
            if is_photo:
                await query.edit_message_caption(
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await query.edit_message_text(
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
    except Exception:
        log.exception("Nie udało się wyświetlić produktu %s", product_id)
        await query.answer("Nie udało się odświeżyć karty produktu.", show_alert=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Witamy w naszym sklepie!</b>\nWybierz katalog, aby zobaczyć produkty.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍 Otwórz katalog", callback_data="catalog")],
            [InlineKeyboardButton("🛒 Koszyk", callback_data="cart")],
        ])
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    cart = context.user_data.setdefault("cart", {})

    if data == "noop":
        return
    if data == "catalog":
        await show_catalog(query)
        return
    if data == "cart":
        await query.edit_message_text(
            cart_text(cart),
            parse_mode="HTML",
            reply_markup=cart_keyboard(cart)
        )
        return
    if data == "clear_cart":
        cart.clear()
        await query.edit_message_text(
            cart_text(cart),
            parse_mode="HTML",
            reply_markup=cart_keyboard(cart)
        )
        return
    if data.startswith("product:"):
        product_id = data.split(":", 1)[1]
        await show_product(query, context, product_id)
        return
    if data.startswith("qty:"):
        _, product_id, quantity = data.split(":")
        await show_product(query, context, product_id, int(quantity))
        return
    if data.startswith("add:"):
        _, product_id, quantity = data.split(":")
        if product_id not in PRODUCT_BY_ID:
            await query.answer("Nie znaleziono produktu.", show_alert=True)
            return
        cart[product_id] = int(cart.get(product_id, 0)) + int(quantity)
        await query.edit_message_text(
            f"✅ Dodano <b>{quantity} szt.</b> produktu "
            f"<b>{PRODUCT_BY_ID[product_id]['name']}</b> do koszyka.\n\n"
            + cart_text(cart),
            parse_mode="HTML",
            reply_markup=cart_keyboard(cart)
        )
        return


def main():
    if not BOT_TOKEN:
        raise RuntimeError("Brak zmiennej środowiskowej BOT_TOKEN w Railway.")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    log.info("Bot uruchomiony. Liczba produktów: %s", len(PRODUCTS))
    app.run_polling()


if __name__ == "__main__":
    main()
