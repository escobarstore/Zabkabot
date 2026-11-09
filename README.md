# Telegram catalogue bot for Railway

This starter project provides:
- /start welcome message and a catalogue button
- 12 editable product entries
- product detail, description and optional photo
- quantity selector
- quantity-based unit pricing
- multi-product cart with quantity adjustment and total
- final cart summary and optional admin chat link

It is a catalogue/cart prototype. It does not collect delivery addresses, process
payments, request BLIK codes, Paysafecard PINs, crypto wallet keys, or claim that
an order/payment has been completed. For real sales, use a properly registered
merchant account and an authorized payment provider with its official checkout.

## Customize products
Edit `products.json`. For every product:
- `name`: displayed name
- `price`: unit price for 1–4 units
- `description`: product details
- `image`: image path in this project (use your own/authorized photos)
- `price_tiers`: minimum quantity and unit price, e.g. 5 units and 10 units

Put image files in `images/` with the filenames shown in `products.json`.
Supported Telegram photo formats include JPEG and PNG.

## Customize Railway variables
Set these in Railway -> Variables:
- `BOT_TOKEN`: token from BotFather (keep it secret)
- `SHOP_NAME`: catalogue/shop display name
- `CURRENCY`: e.g. PLN
- `ADMIN_USERNAME`: Telegram username without @

## Deploy
1. Upload the project to a GitHub repository.
2. In Railway, create a project from that repository.
3. Add the environment variables above.
4. Railway uses `Procfile`/`railway.toml` to start `python bot.py`.

Do not commit your real bot token to GitHub.
