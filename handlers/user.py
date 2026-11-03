from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PAYMENT_ACCOUNTS, OWNER_ID, CHANNEL_ID
from database import (
    get_products, get_all_products, get_product, create_order,
    update_order_status, get_user_orders, add_product, update_product, delete_product
)
from keyboards import payment_method_kb, admin_verify_kb, cod_verify_kb

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

class EditProductState(StatesGroup):
    waiting_id = State()
    waiting_action = State()
    waiting_value = State()
    confirm_delete = State()

# --- Keyboards ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👗 Browse Dresses", callback_data="menu_browse")],
        [InlineKeyboardButton(text="📦 My Orders", callback_data="menu_orders")],
        [InlineKeyboardButton(text="💬 Help & Support", callback_data="menu_help")]
    ])

def checkout_type_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Cash on Delivery (COD)", callback_data=f"checkout_cod_{order_id}")],
        [InlineKeyboardButton(text="💳 Pay Now", callback_data=f"checkout_pay_{order_id}")]
    ])

# ==========================================
# 1. START & MAIN MENU
# ==========================================
@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("buy_"):
        product_id = args[1].replace("buy_", "")
        await process_order_start(message, product_id)
        return

    await message.answer(
        "✨ **Welcome to Dibo Shop!** ✨\n\n"
        "Discover our latest collection of premium dresses. Tap a button below to start shopping.",
        reply_markup=main_menu_kb(), parse_mode="Markdown"
    )

@router.callback_query(F.data == "menu_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "✨ **Main Menu** ✨\n\nWhat would you like to do?",
        reply_markup=main_menu_kb(), parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "💬 **Help & Support**\n\n"
        "• Tap 'Browse Dresses' to see our catalog.\n"
        "• Tap 'My Orders' to check your order status.\n"
        "• For any issues, contact our support: @your_support_username",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]]),
        parse_mode="Markdown"
    )
    await callback.answer()

# ==========================================
# 2. BROWSE PRODUCTS
# ==========================================
@router.callback_query(F.data == "menu_browse")
async def browse_products(callback: CallbackQuery, state: FSMContext):
    products = await get_products()
    if not products:
        await callback.message.edit_text("🛒 Our shop is currently empty.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]]))
        return
    
    await state.update_data(products=products, current_index=0)
    await show_product(callback, state)

async def show_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    products = data.get("products", [])
    idx = data.get("current_index", 0)
    p = products[idx]
    
    caption = f"👗 **{p['name']}**\n\n{p.get('description', '')}\n\n💰 **Price:** {p['price']} ETB\n📦 **In Stock:** {p['stock']}"
    
    nav_buttons = []
    if idx > 0: nav_buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data="prod_prev"))
    nav_buttons.append(InlineKeyboardButton(text="🛍 Buy Now", callback_data=f"prod_buy_{p['_id']}"))
    if idx < len(products) - 1: nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data="prod_next"))
        
    kb = InlineKeyboardMarkup(inline_keyboard=[nav_buttons, [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]])

    try: await callback.message.delete()
    except: pass
        
    if p.get("photo_file_id"): await callback.message.answer_photo(photo=p["photo_file_id"], caption=caption, reply_markup=kb, parse_mode="Markdown")
    else: await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")
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
# 3. CHECKOUT FLOW
# ==========================================
@router.callback_query(F.data.startswith("prod_buy_"))
async def buy_product_inline(callback: CallbackQuery):
    product_id = callback.data.split("_")[2]
    await callback.message.delete()
    await process_order_start(callback.message, product_id, is_callback=True)

async def process_order_start(message: Message, product_id: str, is_callback: bool = False):
    product = await get_product(product_id)
    if not product or product.get("stock", 0) <= 0:
        await message.answer("Sorry, this item is currently out of stock.")
        return

    order_id = await create_order(
        user_id=message.chat.id, username=message.from_user.username if hasattr(message, 'from_user') else message.chat.username,
        items=[{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "qty": 1}],
        total=product["price"]
    )

    caption_text = f"🛒 **Order Summary**\n\nItem: {product['name']}\nTotal: **{product['price']} ETB**\nOrder ID: `{order_id}`\n\n👇 **How would you like to pay?**"
    
    if product.get("photo_file_id"):
        await message.answer_photo(photo=product["photo_file_id"], caption=caption_text, reply_markup=checkout_type_kb(order_id), parse_mode="Markdown")
    else:
        await message.answer(caption_text, reply_markup=checkout_type_kb(order_id), parse_mode="Markdown")

# --- COD FLOW ---
@router.callback_query(F.data.startswith("checkout_cod_"))
async def checkout_cod(callback: CallbackQuery):
    order_id = callback.data.split("_")[2]
    order = await get_order(order_id)
    await update_order_status(order_id, "cod_pending")
    
    await callback.bot.send_message(
        chat_id=OWNER_ID,
        text=f"📦 **New COD Order!**\nOrder: `{order_id}`\nUser: @{callback.from_user.username}\nTotal: {order['total']} ETB\n\nDeliver and collect cash.",
        reply_markup=cod_verify_kb(order_id), parse_mode="Markdown"
    )
    
    await callback.message.edit_caption(caption="✅ **Order Confirmed!**\n\nYou chose Cash on Delivery. Please wait for our delivery agent to contact you.", parse_mode="Markdown")
    await callback.answer()

# --- PAY NOW FLOW ---
@router.callback_query(F.data.startswith("checkout_pay_"))
async def checkout_pay(callback: CallbackQuery, state: FSMContext):
    order_id = callback.data.split("_")[2]
    await callback.message.edit_caption(
        caption="💳 **Select Payment Method**\n\nPlease choose your bank to see the account details.",
        reply_markup=payment_method_kb(order_id), parse_mode="Markdown"
    )
    await state.update_data(order_id=order_id)
    await state.set_state(OrderState.waiting_screenshot)
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def select_payment(callback: CallbackQuery, state: FSMContext):
    _, method, order_id = callback.data.split("_", 2)
    account_info = PAYMENT_ACCOUNTS.get(method, "Account info not configured.")
    await update_order_status(order_id, "pending_payment")

    await callback.message.edit_caption(
        caption=f"💳 **Payment: {method.upper()}**\n\nPlease transfer to:\n`{account_info}`\n\nAfter payment, **send a screenshot** of the receipt here.",
        parse_mode="Markdown"
    )
    await state.update_data(order_id=order_id, method=method)
    await callback.answer()

@router.message(OrderState.waiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")

    await message.bot.send_photo(
        chat_id=OWNER_ID, photo=message.photo[-1].file_id,
        caption=f"🚨 **New Payment Proof** 🚨\nOrder: `{order_id}`\nUser: @{message.from_user.username or message.from_user.id}\n\nVerify the transaction then click below.",
        parse_mode="Markdown", reply_markup=admin_verify_kb(order_id)
    )

    await message.answer("✅ Screenshot received! Our team will verify it shortly.", reply_markup=main_menu_kb())
    await state.clear()

# ==========================================
# 4. MY ORDERS
# ==========================================
@router.callback_query(F.data == "menu_orders")
async def my_orders(callback: CallbackQuery):
    orders = await get_user_orders(callback.from_user.id)
    if not orders:
        await callback.message.edit_text("📭 You have no orders yet.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👗 Browse Dresses", callback_data="menu_browse")]]))
        return
        
    text = "📦 **Your Recent Orders:**\n\n"
    for o in orders:
        status_emoji = "⏳" if "pending" in o['status'] else ("✅" if o['status'] == "paid" else ("🚚" if o['status'] == "delivered" else "❌"))
        text += f"{status_emoji} `{o['_id']}` — {o['total']} ETB — **{o['status'].replace('_', ' ').title()}**\n"
        
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]]), parse_mode="Markdown")

# ==========================================
# 5. ADMIN: ADD PRODUCT (OWNER ONLY)
# ==========================================
@router.message(F.text == "/addproduct")
async def cmd_addproduct(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return await message.answer("⛔ You are not authorized to use this command.")
        
    await message.answer("📸 Send me a **photo** of the dress.")
    await state.set_state(AddProductState.waiting_photo)

@router.message(AddProductState.waiting_photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("✅ Photo saved. Now send me the **Name** of the dress.")
    await state.set_state(AddProductState.waiting_name)

@router.message(AddProductState.waiting_name)
async def add_name(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await state.update_data(name=message.text)
    await message.answer("✅ Name saved. Now send the **Price** (numbers only).")
    await state.set_state(AddProductState.waiting_price)

@router.message(AddProductState.waiting_price)
async def add_price(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        await state.update_data(price=float(message.text))
        await message.answer("✅ Price saved. Now send a short **Description**.")
        await state.set_state(AddProductState.waiting_desc)
    except:
        await message.answer("❌ Invalid number. Send the price again.")

@router.message(AddProductState.waiting_desc)
async def add_desc(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    await state.update_data(desc=message.text)
    await message.answer("✅ Description saved. Finally, how many items are **In Stock**?")
    await state.set_state(AddProductState.waiting_stock)

@router.message(AddProductState.waiting_stock)
async def add_stock(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        stock = int(message.text)
        data = await state.get_data()
        product_id = await add_product(name=data['name'], price=data['price'], description=data['desc'], photo_file_id=data['photo'], stock=stock)
        await state.update_data(product_id=product_id, stock=stock)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Yes, Post to Channel", callback_data="post_channel")], [InlineKeyboardButton(text="❌ No, Just Save", callback_data="post_cancel")]])
        await message.answer(f"🎉 Product saved! Do you want to post this to your Channel now?", reply_markup=kb)
        await state.set_state(AddProductState.confirm_post)
    except:
        await message.answer("❌ Invalid number. Send the stock quantity again.")

@router.callback_query(F.data == "post_channel", AddProductState.confirm_post)
async def post_to_channel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    data = await state.get_data()
    
    bot_info = await callback.bot.get_me()
    buy_link = f"https://t.me/{bot_info.username}?start=buy_{data['product_id']}"
    
    channel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛍 Order Now", url=buy_link)]])
    caption = f"✨ **{data['name']}** ✨\n\n{data['desc']}\n\n💰 **Price:** {data['price']} ETB\n📦 **Stock:** {data['stock']} items left!\n\n👇 Tap below to order directly."
    
    try:
        if CHANNEL_ID != 0:
            await callback.bot.send_photo(chat_id=CHANNEL_ID, photo=data['photo'], caption=caption, reply_markup=channel_kb, parse_mode="Markdown")
            await callback.message.edit_text("✅ Product posted to the Channel!")
        else:
            await callback.message.edit_text("⚠️ CHANNEL_ID is not set.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Failed to post: {e}")
    await state.clear()

@router.callback_query(F.data == "post_cancel", AddProductState.confirm_post)
async def cancel_post(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await callback.message.edit_text("✅ Product saved (not posted).")
    await state.clear()

# ==========================================
# 6. ADMIN: EDIT & DELETE PRODUCT (OWNER ONLY)
# ==========================================
@router.message(F.text == "/editproduct")
async def cmd_editproduct(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return await message.answer("⛔ Unauthorized.")
        
    products = await get_all_products()
    if not products:
        return await message.answer("No products found in DB.")
    
    text = "Send the **Product ID** you want to edit/delete:\n\n"
    for p in products:
        text += f"`{p['_id']}` — {p['name']} (Stock: {p['stock']}, Price: {p['price']})\n"
    
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(EditProductState.waiting_id)

@router.message(EditProductState.waiting_id)
async def edit_id(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    product = await get_product(message.text.strip())
    if not product:
        return await message.answer("❌ Invalid ID. Try again.")
    
    await state.update_data(edit_id=message.text.strip(), product_name=product['name'])
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Update Photo", callback_data="edit_photo")],
        [InlineKeyboardButton(text="📝 Update Name", callback_data="edit_name")],
        [InlineKeyboardButton(text="📄 Update Description", callback_data="edit_description")],
        [InlineKeyboardButton(text="💰 Update Price", callback_data="edit_price")],
        [InlineKeyboardButton(text="📦 Update Stock", callback_data="edit_stock")],
        [InlineKeyboardButton(text="🗑 DELETE PRODUCT", callback_data="edit_delete")]
    ])
    await message.answer(f"Editing **{product['name']}**.\nWhat do you want to change?", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(EditProductState.waiting_action)

@router.callback_query(F.data == "edit_delete", EditProductState.waiting_action)
async def confirm_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ YES, Delete Forever", callback_data="confirm_delete_yes")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="menu_main")]
    ])
    await callback.message.edit_text(f"⚠️ Are you sure you want to delete **{data['product_name']}**? This cannot be undone.", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(EditProductState.confirm_delete)
    await callback.answer()

@router.callback_query(F.data == "confirm_delete_yes", EditProductState.confirm_delete)
async def execute_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await delete_product(data['edit_id'])
    await callback.message.edit_text("🗑 **Product Deleted Successfully.**")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("edit_"), EditProductState.waiting_action)
async def edit_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[1]
    await state.update_data(edit_field=field)
    
    if field == "photo":
        await callback.message.edit_text("📸 Send the **new Photo** for this product:")
    else:
        await callback.message.edit_text(f"Send the **new {field.title()}** value:")
        
    await state.set_state(EditProductState.waiting_value)
    await callback.answer()

@router.message(EditProductState.waiting_value, F.photo)
async def edit_photo_value(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    if data['edit_field'] == "photo":
        await update_product(data['edit_id'], {"photo_file_id": message.photo[-1].file_id})
        await message.answer("✅ Product photo updated successfully!")
        await state.clear()
    else:
        await message.answer("❌ Please send text, not a photo.")

@router.message(EditProductState.waiting_value)
async def edit_text_value(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    field = data['edit_field']
    
    if field == "photo":
        return await message.answer("❌ Please send a photo, not text.")
        
    val = message.text.strip()
    
    try:
        if field == "price": val = float(val)
        elif field == "stock": val = int(val)
        
        await update_product(data['edit_id'], {field: val})
        await message.answer(f"✅ Product updated! **{field.title()}** is now: `{val}`", parse_mode="Markdown")
    except:
        await message.answer("❌ Invalid value format. Please try again.")
        
    await state.clear()
