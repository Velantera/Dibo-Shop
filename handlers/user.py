from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PAYMENT_ACCOUNTS, ADMIN_GROUP_ID, CHANNEL_ID
from database import (
    get_products, get_product, create_order,
    update_payment_method, get_user_orders, add_product
)
from keyboards import payment_method_kb, admin_verify_kb

router = Router()

# --- FSM States ---
class OrderState(StatesGroup):
    waiting_screenshot = State()

class AddProductState(StatesGroup):
    waiting_photo = State()
    waiting_name = State()
    waiting_price = State()
    waiting_desc = State()
    waiting_stock = State()
    confirm_post = State()

# --- Keyboards ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👗 Browse Dresses", callback_data="menu_browse")],
        [InlineKeyboardButton(text="📦 My Orders", callback_data="menu_orders")],
        [InlineKeyboardButton(text="💬 Help & Support", callback_data="menu_help")]
    ])

# ==========================================
# 1. START & MAIN MENU
# ==========================================
@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message, state: FSMContext):
    # Clear any stuck states
    await state.clear()
    
    args = message.text.split()
    # Deep Linking: If user clicked "Buy Now" from the channel
    if len(args) > 1 and args[1].startswith("buy_"):
        product_id = args[1].replace("buy_", "")
        await process_buy_now(message, product_id)
        return

    await message.answer(
        "✨ **Welcome to Dibo Shop!** ✨\n\n"
        "Discover our latest collection of premium dresses. Tap a button below to start shopping.",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "menu_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "✨ **Main Menu** ✨\n\nWhat would you like to do?",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown"
    )
    await callback.answer()

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

# ==========================================
# 2. BROWSE PRODUCTS (Pagination)
# ==========================================
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

# ==========================================
# 3. BUY & PAYMENT FLOW
# ==========================================
@router.callback_query(F.data.startswith("prod_buy_"))
async def buy_product_inline(callback: CallbackQuery):
    product_id = callback.data.split("_")[2]
    await callback.message.delete()
    await process_buy_now(callback.message, product_id, is_callback=True)

async def process_buy_now(message: Message, product_id: str, is_callback: bool = False):
    product = await get_product(product_id)
    
    if not product or product.get("stock", 0) <= 0:
        if is_callback:
            await message.answer("Sorry, this item just went out of stock!")
        else:
            await message.answer("Sorry, this item is currently out of stock.")
        return

    order_id = await create_order(
        user_id=message.chat.id, # Works for both Callback and Message
        username=message.from_user.username if hasattr(message, 'from_user') else message.chat.username,
        items=[{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "qty": 1}],
        total=product["price"],
    )

    caption_text = (
        f"🛒 **Order Summary**\n\n"
        f"Item: {product['name']}\n"
        f"Total: **{product['price']} ETB**\n"
        f"Order ID: `{order_id}`\n\n"
        f"👇 **Please select a payment method to proceed:**"
    )
    
    if product.get("photo_file_id"):
        await message.answer_photo(
            photo=product["photo_file_id"], caption=caption_text,
            reply_markup=payment_method_kb(order_id), parse_mode="Markdown"
        )
    else:
        await message.answer(caption_text, reply_markup=payment_method_kb(order_id), parse_mode="Markdown")

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
        reply_markup=main_menu_kb()
    )
    await state.clear()

@router.message(OrderState.waiting_screenshot)
async def wrong_input(message: Message):
    await message.answer("⚠️ Please send a **photo** of your payment receipt.", parse_mode="Markdown")

# ==========================================
# 4. MY ORDERS
# ==========================================
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

# ==========================================
# 5. ADMIN: ADD PRODUCT & POST TO CHANNEL
# ==========================================
@router.message(F.text == "/addproduct")
async def cmd_addproduct(message: Message, state: FSMContext):
    await message.answer("📸 Send me a **photo** of the dress.")
    await state.set_state(AddProductState.waiting_photo)

@router.message(AddProductState.waiting_photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("✅ Photo saved. Now send me the **Name** of the dress.")
    await state.set_state(AddProductState.waiting_name)

@router.message(AddProductState.waiting_name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("✅ Name saved. Now send the **Price** (numbers only, e.g., 1500).")
    await state.set_state(AddProductState.waiting_price)

@router.message(AddProductState.waiting_price)
async def add_price(message: Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price=price)
        await message.answer("✅ Price saved. Now send a short **Description**.")
        await state.set_state(AddProductState.waiting_desc)
    except ValueError:
        await message.answer("❌ Invalid number. Please send the price again (e.g., 1500).")

@router.message(AddProductState.waiting_desc)
async def add_desc(message: Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("✅ Description saved. Finally, how many items are **In Stock**? (e.g., 10)")
    await state.set_state(AddProductState.waiting_stock)

@router.message(AddProductState.waiting_stock)
async def add_stock(message: Message, state: FSMContext):
    try:
        stock = int(message.text)
        data = await state.get_data()
        
        product_id = await add_product(
            name=data['name'], price=data['price'], description=data['desc'],
            photo_file_id=data['photo'], stock=stock
        )
        
        await state.update_data(product_id=product_id, stock=stock)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Yes, Post to Channel", callback_data="post_channel")],
            [InlineKeyboardButton(text="❌ No, Just Save", callback_data="post_cancel")]
        ])
        await message.answer(
            f"🎉 Product saved to database!\n\nDo you want to post this to your Channel/Group now?",
            reply_markup=kb
        )
        await state.set_state(AddProductState.confirm_post)
    except ValueError:
        await message.answer("❌ Invalid number. Please send the stock quantity again.")

@router.callback_query(F.data == "post_channel", AddProductState.confirm_post)
async def post_to_channel(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_id = data['product_id']
    
    bot_info = await callback.bot.get_me()
    buy_link = f"https://t.me/{bot_info.username}?start=buy_{product_id}"
    
    channel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Buy Now", url=buy_link)]
    ])
    
    caption = (
        f"✨ **{data['name']}** ✨\n\n"
        f"{data['desc']}\n\n"
        f"💰 **Price:** {data['price']} ETB\n"
        f"📦 **Stock:** {data['stock']} items left!\n\n"
        f"👇 Tap below to order directly via our bot."
    )
    
    try:
        if CHANNEL_ID != 0:
            await callback.bot.send_photo(
                chat_id=CHANNEL_ID, photo=data['photo'], caption=caption, 
                reply_markup=channel_kb, parse_mode="Markdown"
            )
            await callback.message.edit_text("✅ Product posted to the Channel successfully!")
        else:
            await callback.message.edit_text("⚠️ CHANNEL_ID is not set in your config.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Failed to post to channel. Error: {e}")
        
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "post_cancel", AddProductState.confirm_post)
async def cancel_post(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Product saved (not posted to channel).")
    await state.clear()
    await callback.answer()
