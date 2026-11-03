from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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

# --- Main Menu Keyboard ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👗 Browse Dresses", callback_data="menu_browse")],
        [InlineKeyboardButton(text="📦 My Orders", callback_data="menu_orders")],
        [InlineKeyboardButton(text="💬 Help & Support", callback_data="menu_help")]
    ])

# --- 1. START COMMAND ---
@router.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer(
        "✨ **Welcome to Dibo Shop!** ✨\n\n"
        "Discover our latest collection of premium dresses. Tap a button below to start shopping.",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )

# --- 2. MAIN MENU HANDLERS ---
@router.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "💬 **Help & Support**\n\n"
        "• Tap 'Browse Dresses' to see our catalog.\n"
        "• Tap 'My Orders' to check your order status.\n"
        "• For any issues, contact our support: @your_support_username",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "menu_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "✨ **Main Menu** ✨\n\nWhat would you like to do?",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

# --- 3. BROWSE PRODUCTS (Pagination) ---
@router.callback_query(F.data == "menu_browse")
async def browse_products(callback: CallbackQuery, state: FSMContext):
    products = await get_products()
    if not products:
        await callback.message.edit_text(
            "🛒 Our shop is currently empty. Check back soon!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]
            ])
        )
        await callback.answer()
        return
    
    await state.update_data(products=products, current_index=0)
    await show_product(callback, state)

async def show_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    products = data.get("products", [])
    idx = data.get("current_index", 0)
    
    if not products:
        await callback.message.edit_text("No products available.")
        return

    p = products[idx]
    caption = (
        f"👗 **{p['name']}**\n\n"
        f"{p.get('description', 'No description.')}\n\n"
        f"💰 **Price:** {p['price']} ETB\n"
        f"📦 **In Stock:** {p['stock']}"
    )
    
    # Pagination controls
    nav_buttons = []
    if idx > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data="prod_prev"))
    nav_buttons.append(InlineKeyboardButton(text="🛍 Buy Now", callback_data=f"prod_buy_{p['_id']}"))
    if idx < len(products) - 1:
        nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data="prod_next"))
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        nav_buttons,
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]
    ])

    # If editing a message with a photo, we delete and send a new one to avoid errors
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    if p.get("photo_file_id"):
        await callback.message.answer_photo(
            photo=p["photo_file_id"], caption=caption, reply_markup=kb, parse_mode="Markdown"
        )
    else:
        await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")
        
    await callback.answer()

@router.callback_query(F.data == "prod_prev")
async def prev_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data.get("current_index", 0)
    if idx > 0:
        await state.update_data(current_index=idx - 1)
        await show_product(callback, state)

@router.callback_query(F.data == "prod_next")
async def next_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data.get("current_index", 0)
    products = data.get("products", [])
    if idx < len(products) - 1:
        await state.update_data(current_index=idx + 1)
        await show_product(callback, state)

# --- 4. ORDER FLOW ---
@router.callback_query(F.data.startswith("prod_buy_"))
async def buy_product(callback: CallbackQuery):
    product_id = callback.data.split("_")[2]
    product = await get_product(product_id)
    
    if not product or product.get("stock", 0) <= 0:
        await callback.answer("Sorry, this item just went out of stock!", show_alert=True)
        return

    order_id = await create_order(
        user_id=callback.from_user.id,
        username=callback.from_user.username or callback.from_user.full_name,
        items=[{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "qty": 1}],
        total=product["price"],
    )

    await callback.message.edit_caption(
        caption=(
            f"🛒 **Order Summary**\n\n"
            f"Item: {product['name']}\n"
            f"Total: **{product['price']} ETB**\n"
            f"Order ID: `{order_id}`\n\n"
            f"👇 **Please select a payment method to proceed:**"
        ),
        reply_markup=payment_method_kb(order_id),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def select_payment(callback: CallbackQuery, state: FSMContext):
    _, method, order_id = callback.data.split("_", 2)
    account_info = PAYMENT_ACCOUNTS.get(method, "Account info not configured.")

    await update_payment_method(order_id, method)

    await callback.message.edit_caption(
        caption=(
            f"💳 **Payment Method: {method.upper()}**\n\n"
            f"Please transfer to:\n`{account_info}`\n\n"
            f"After payment, **send a screenshot** of the receipt here.\n"
            f"Our team will verify it and confirm your order."
        ),
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
            f"🚨 **New Payment Proof** 🚨\n"
            f"Order: `{order_id}`\n"
            f"User: @{message.from_user.username or message.from_user.id}\n"
            f"Verify the transaction then click below."
        ),
        parse_mode="Markdown",
        reply_markup=admin_verify_kb(order_id)
    )

    await message.answer(
        "✅ Screenshot received! Our team will verify it shortly. You will be notified once approved.",
        reply_markup=main_menu_kb() # Bring them back to the menu
    )
    await state.clear()

@router.message(OrderState.waiting_screenshot)
async def wrong_input(message: Message):
    await message.answer("⚠️ Please send a **photo** of your payment receipt.", parse_mode="Markdown")

# --- 5. MY ORDERS ---
@router.callback_query(F.data == "menu_orders")
async def my_orders(callback: CallbackQuery):
    orders = await get_user_orders(callback.from_user.id)
    
    if not orders:
        await callback.message.edit_text(
            "📭 You have no orders yet. Time to go shopping!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👗 Browse Dresses", callback_data="menu_browse")],
                [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]
            ])
        )
        await callback.answer()
        return
        
    text = "📦 **Your Recent Orders:**\n\n"
    for o in orders:
        status_emoji = "⏳" if o['status'] == "pending_payment" else ("✅" if o['status'] == "paid" else "❌")
        text += f"{status_emoji} `{o['_id']}` — {o['total']} ETB — **{o['status'].replace('_', ' ').title()}**\n"
        
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()
