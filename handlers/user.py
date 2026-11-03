from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PAYMENT_ACCOUNTS
from database import get_products, create_order
from keyboards import payment_method_kb

router = Router()

class OrderState(StatesGroup):
    waiting_screenshot = State()

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(
        "Welcome to the Dress Shop! 👗\n\n"
        "Commands:\n"
        "/products — Browse items\n"
        "/help — Support"
    )

@router.message(F.text == "/products")
async def list_products(message: Message):
    products = await get_products()
    if not products:
        await message.answer("No products available yet.")
        return
    for pid, name, price, desc, photo, stock in products:
        caption = f"**{name}**\n{desc}\n💰 {price} ETB\n📦 Stock: {stock}"
        if photo:
            await message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")
        else:
            await message.answer(caption, parse_mode="Markdown")

@router.message(F.text.regexp(r"^/buy (\d+)$"))
async def buy_product(message: Message, state: FSMContext):
    # Simplified: one-click purchase of a single item; in practice, cart logic can be added
    product_id = int(message.text.split()[1])
    products = await get_products()
    product = next((p for p in products if p[0] == product_id), None)
    if not product:
        await message.answer("Product not found.")
        return

    order_id = await create_order(
        user_id=message.from_user.id,
        username=message.from_user.username or message.from_user.full_name,
        items=[{"id": product[0], "name": product[1], "price": product[2], "qty": 1}],
        total=product[2],
        payment_method="pending"
    )

    await message.answer(
        f"Order #{order_id} created.\nTotal: {product[2]} ETB\n\nPlease select payment method:",
        reply_markup=payment_method_kb(order_id)
    )

@router.callback_query(F.data.startswith("pay_"))
async def select_payment(callback: CallbackQuery, state: FSMContext):
    _, method, order_id_str = callback.data.split("_")
    order_id = int(order_id_str)
    account_info = PAYMENT_ACCOUNTS.get(method, "Account info not configured.")

    await callback.message.edit_text(
        f"**Payment Method: {method.upper()}**\n\n"
        f"Please transfer to:\n`{account_info}`\n\n"
        f"After payment, **send a screenshot** of the receipt here.\n"
        f"The admin will verify and confirm your order.",
        parse_mode="Markdown"
    )

    # Update order payment method
    from database import update_order_status
    import aiosqlite
    async with aiosqlite.connect("shop.db") as db:
        await db.execute("UPDATE orders SET payment_method = ? WHERE id = ?", (method, order_id))
        await db.commit()

    await state.update_data(order_id=order_id)
    await state.set_state(OrderState.waiting_screenshot)
    await callback.answer()

@router.message(OrderState.waiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")

    # Forward to admin group
    from config import ADMIN_GROUP_ID
    from keyboards import admin_verify_kb

    await message.bot.send_photo(
        chat_id=ADMIN_GROUP_ID,
        photo=message.photo[-1].file_id,
        caption=(
            f"**New Payment Proof**\n"
            f"Order: #{order_id}\n"
            f"User: @{message.from_user.username or message.from_user.id}\n"
            f"Please verify the transaction and click below."
        ),
        parse_mode="Markdown",
        reply_markup=admin_verify_kb(order_id)
    )

    await message.answer("✅ Screenshot received! Admin will verify shortly. You will be notified once approved.")
    await state.clear()
