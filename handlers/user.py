from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PAYMENT_ACCOUNTS, ADMIN_GROUP_ID
from database import (
    get_products, get_product, create_order,
    update_payment_method, get_user_orders
)
from keyboards import payment_method_kb, admin_verify_kb

router = Router()

class OrderState(StatesGroup):
    waiting_screenshot = State()

# ---------- Commands ----------

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(
        "Welcome to the Dress Shop! 👗\n\n"
        "Commands:\n"
        "/products — Browse items\n"
        "/myorders — View your orders\n"
        "/help — Contact support"
    )

@router.message(F.text == "/help")
async def cmd_help(message: Message):
    await message.answer(
        "Need help?\n"
        "• Send /products to browse\n"
        "• Send /myorders to check order status\n"
        "• For anything else, message @your_support_username"
    )

@router.message(F.text == "/products")
async def list_products(message: Message):
    products = await get_products()
    if not products:
        await message.answer("No products available yet. Check back soon!")
        return
    for p in products:
        caption = (
            f"**{p['name']}**\n"
            f"{p.get('description', '')}\n"
            f"💰 {p['price']} ETB\n"
            f"📦 Stock: {p['stock']}\n\n"
            f"Order: `/buy {p['_id']}`"
        )
        if p.get("photo_file_id"):
            await message.answer_photo(photo=p["photo_file_id"], caption=caption, parse_mode="Markdown")
        else:
            await message.answer(caption, parse_mode="Markdown")

@router.message(F.text.regexp(r"^/buy\s+([a-f0-9]{24})$"))
async def buy_product(message: Message):
    product_id = message.text.split()[1]
    product = await get_product(product_id)
    if not product or product.get("stock", 0) <= 0:
        await message.answer("Product not available.")
        return

    order_id = await create_order(
        user_id=message.from_user.id,
        username=message.from_user.username or message.from_user.full_name,
        items=[{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "qty": 1}],
        total=product["price"],
    )

    await message.answer(
        f"Order created: `{order_id}`\n"
        f"Total: **{product['price']} ETB**\n\n"
        f"Please select a payment method:",
        parse_mode="Markdown",
        reply_markup=payment_method_kb(order_id)
    )

@router.message(F.text == "/myorders")
async def my_orders(message: Message):
    orders = await get_user_orders(message.from_user.id)
    if not orders:
        await message.answer("You have no orders yet.")
        return
    lines = []
    for o in orders:
        lines.append(
            f"• `{o['_id']}` — {o['total']} ETB — **{o['status']}**"
        )
    await message.answer("Your orders:\n\n" + "\n".join(lines), parse_mode="Markdown")

# ---------- Payment flow ----------

@router.callback_query(F.data.startswith("pay_"))
async def select_payment(callback: CallbackQuery, state: FSMContext):
    _, method, order_id = callback.data.split("_", 2)
    account_info = PAYMENT_ACCOUNTS.get(method, "Account info not configured.")

    await update_payment_method(order_id, method)

    await callback.message.edit_text(
        f"**Payment Method: {method.upper()}**\n\n"
        f"Please transfer to:\n`{account_info}`\n\n"
        f"After payment, **send a screenshot** of the receipt here.\n"
        f"The admin will verify and confirm your order.",
        parse_mode="Markdown"
    )

    await state.update_data(order_id=order_id)
    await state.set_state(OrderState.waiting_screenshot)
    await callback.answer()

@router.message(OrderState.waiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")

    await message.bot.send_photo(
        chat_id=ADMIN_GROUP_ID,
        photo=message.photo[-1].file_id,
        caption=(
            f"**New Payment Proof**\n"
            f"Order: `{order_id}`\n"
            f"User: @{message.from_user.username or message.from_user.id}\n"
            f"Verify the transaction then click below."
        ),
        parse_mode="Markdown",
        reply_markup=admin_verify_kb(order_id)
    )

    await message.answer(
        "✅ Screenshot received! Admin will verify shortly. "
        "You'll be notified once approved."
    )
    await state.clear()

@router.message(OrderState.waiting_screenshot)
async def wrong_input(message: Message):
    await message.answer("Please send a **photo** of your payment receipt.", parse_mode="Markdown")
