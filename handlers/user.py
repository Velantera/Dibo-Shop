from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PAYMENT_ACCOUNTS, OWNER_ID, CHANNEL_ID
from database import (
    get_products, get_all_products, get_product, create_order,
    update_order_status, get_user_orders, add_product, update_product, delete_product,
    get_order, update_order_address
)
from keyboards import payment_method_kb, admin_verify_kb, cod_verify_kb

router = Router()

# --- FSM States ---
class OrderState(StatesGroup):
    waiting_address = State() # <-- NEW
    waiting_screenshot = State()

class AddProductState(StatesGroup):
    waiting_photo = State()
    waiting_name = State()
    waiting_price = State()
    waiting_desc = State()
    waiting_stock = State()
    waiting_sizes = State()
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

def size_selection_kb(sizes: list, product_id: str):
    buttons = []
    row = []
    for size in sizes:
        row.append(InlineKeyboardButton(text=size, callback_data=f"selectsize_{size}_{product_id}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==========================================
# 1. START & MAIN MENU
# ==========================================
@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith("buy_"):
        product_id = args[1].replace("buy_", "")
        await show_size_selection(message, product_id)
        return

    await message.answer(
        "✨ **Welcome to Dibo Shop!** ✨\n\n"
        "Discover our latest collection of premium dresses. Tap a button below to start shopping.",
        reply_markup=main_menu_kb(), parse_mode="Markdown"
    )

@router.callback_query(F.data == "menu_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(
            "✨ **Main Menu** ✨\n\nWhat would you like to do?",
            reply_markup=main_menu_kb(), parse_mode="Markdown"
        )
    except Exception:
        await callback.message.answer("✨ **Main Menu** ✨", reply_markup=main_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "💬 **Help & Support**\n\n"
            "• Tap 'Browse Dresses' to see our catalog.\n"
            "• Tap 'My Orders' to check your order status.\n"
            "• For any issues, contact our support: @your_support_username",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await callback.answer()

# ==========================================
# 2. BROWSE PRODUCTS
# ==========================================
@router.callback_query(F.data == "menu_browse")
async def browse_products(callback: CallbackQuery, state: FSMContext):
    products = await get_products()
    if not products:
        try:
            await callback.message.edit_text("🛒 Our shop is currently empty.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]]))
        except Exception:
            pass
        await callback.answer()
        return
    
    await state.update_data(products=products, current_index=0)
    await show_product(callback, state)

async def show_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    products = data.get("products", [])
    idx = data.get("current_index", 0)
    p = products[idx]
    
    sizes_text = ", ".join(p.get("sizes", [])) if p.get("sizes") else "One Size"
    caption = f"👗 **{p['name']}**\n\n{p.get('description', '')}\n\n📏 **Sizes:** {sizes_text}\n💰 **Price:** {p['price']} ETB\n📦 **In Stock:** {p['stock']}"
    
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
    else:
        await callback.answer()

@router.callback_query(F.data == "prod_next")
async def next_product(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data.get("current_index", 0)
    products = data.get("products", [])
    if idx < len(products) - 1:
        await state.update_data(current_index=idx + 1)
        await show_product(callback, state)
    else:
        await callback.answer()

# ==========================================
# 3. CHECKOUT & SIZE SELECTION
# ==========================================
@router.callback_query(F.data.startswith("prod_buy_"))
async def buy_product_inline(callback: CallbackQuery):
    product_id = callback.data.split("_")[2]
    await callback.message.delete()
    await show_size_selection(callback.message, product_id)

async def show_size_selection(message: Message, product_id: str):
    product = await get_product(product_id)
    if not product or product.get("stock", 0) <= 0:
        return await message.answer("Sorry, this item is currently out of stock.")

    sizes = product.get("sizes", [])
    if not sizes:
        # If no sizes, skip straight to address prompt
        await prompt_for_address(message, product_id, size="One Size")
        return

    await message.answer(
        f"📏 **Select a size for {product['name']}:**",
        reply_markup=size_selection_kb(sizes, product_id)
    )

@router.callback_query(F.data.startswith("selectsize_"))
async def size_selected(callback: CallbackQuery):
    parts = callback.data.split("_")
    size = parts[1]
    product_id = parts[2]
    
    await callback.message.delete()
    await prompt_for_address(callback.message, product_id, size)
    await callback.answer()

# --- NEW: PROMPT FOR ADDRESS ---
async def prompt_for_address(message: Message, product_id: str, size: str):
    product = await get_product(product_id)
    
    # Create the order in the DB right away
    order_id = await create_order(
        user_id=message.chat.id, username=message.from_user.username if hasattr(message, 'from_user') else message.chat.username,
        items=[{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "qty": 1, "size": size}],
        total=product["price"]
    )

    # Store order_id and product info in state so we can use it after they type the address
    # Note: We need to pass the state along, so we use a hack here to set it in the next handler
    
    await message.answer(
        "📍 **Delivery Address Required**\n\n"
        "Please type your **Delivery Address** (Sub-city, Woreda, and a nearby landmark).\n\n"
        "*Example: Bole, Woreda 03, near Edna Mall*",
        parse_mode="Markdown"
    )
    
    # We return the order_id so the next handler can use it
    return order_id

@router.message(OrderState.waiting_address) # We will set this state after size selection
async def save_address(message: Message, state: FSMContext):
    # This won't work directly unless we set the state properly. 
    # Let's fix the flow below.
    pass

# --- FIXING THE FLOW ---
# Because we need to set the state when we ask for the address, we update the prompt_for_address function
# Replace the above prompt_for_address and save_address with this:

async def prompt_for_address_updated(message: Message, product_id: str, size: str, state: FSMContext):
    product = await get_product(product_id)
    
    order_id = await create_order(
        user_id=message.chat.id, username=message.from_user.username if hasattr(message, 'from_user') else message.chat.username,
        items=[{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "qty": 1, "size": size}],
        total=product["price"]
    )

    await state.update_data(order_id=order_id)
    await state.set_state(OrderState.waiting_address)

    await message.answer(
        "📍 **Delivery Address Required**\n\n"
        "Please type your **Delivery Address** (Sub-city, Woreda, and a nearby landmark).\n\n"
        "*Example: Bole, Woreda 03, near Edna Mall*",
        parse_mode="Markdown"
    )

# --- Update the size selection to use the new function ---
@router.callback_query(F.data.startswith("selectsize_"))
async def size_selected_updated(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    size = parts[1]
    product_id = parts[2]
    
    await callback.message.delete()
    await prompt_for_address_updated(callback.message, product_id, size, state)
    await callback.answer()

# --- Update the show_size_selection to pass state ---
async def show_size_selection_updated(message: Message, product_id: str, state: FSMContext):
    product = await get_product(product_id)
    if not product or product.get("stock", 0) <= 0:
        return await message.answer("Sorry, this item is currently out of stock.")

    sizes = product.get("sizes", [])
    if not sizes:
        await prompt_for_address_updated(message, product_id, size="One Size", state=state)
        return

    await message.answer(
        f"📏 **Select a size for {product['name']}:**",
        reply_markup=size_selection_kb(sizes, product_id)
    )

# --- Update the buy button to pass state ---
@router.callback_query(F.data.startswith("prod_buy_"))
async def buy_product_inline_updated(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.split("_")[2]
    await callback.message.delete()
    await show_size_selection_updated(callback.message, product_id, state)

# --- Update the start command to pass state ---
@router.message(F.text.startswith("/start"))
async def cmd_start_updated(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    
    if len(args) > 1 and args[1].startswith("buy_"):
        product_id = args[1].replace("buy_", "")
        await show_size_selection_updated(message, product_id, state)
        return

    await message.answer(
        "✨ **Welcome to Dibo Shop!** ✨\n\n"
        "Discover our latest collection of premium dresses. Tap a button below to start shopping.",
        reply_markup=main_menu_kb(), parse_mode="Markdown"
    )

# --- Handle the address input and show payment options ---
@router.message(OrderState.waiting_address)
async def receive_address(message: Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 10:
        return await message.answer("❌ Address is too short. Please provide Sub-city, Woreda, and Landmark.")
    
    data = await state.get_data()
    order_id = data.get("order_id")
    
    await update_order_address(order_id, address)
    
    order = await get_order(order_id)
    item = order['items'][0]
    
    await message.answer(
        f"📍 **Address Saved:**\n_{address}_\n\n"
        f"🛒 **Order Summary**\n"
        f"Item: {item['name']}\n"
        f"Size: **{item.get('size')}**\n"
        f"Total: **{order['total']} ETB**\n"
        f"Order ID: `{order_id}`\n\n"
        f"👇 **How would you like to pay?**",
        reply_markup=checkout_type_kb(order_id),
        parse_mode="Markdown"
    )
    await state.clear()

# --- COD FLOW (FIXED WITH ADDRESS) ---
@router.callback_query(F.data.startswith("checkout_cod_"))
async def checkout_cod(callback: CallbackQuery):
    try:
        order_id = callback.data.split("_")[2]
        order = await get_order(order_id)
        
        if not order:
            await callback.answer("Order not found.", show_alert=True)
            return

        await update_order_status(order_id, "cod_pending")
        
        item = order['items'][0]
        address = order.get('address', 'Not provided')
        
        # 1. Notify Owner
        await callback.bot.send_message(
            chat_id=OWNER_ID,
            text=f"📦 **New COD Order!**\nOrder: `{order_id}`\nUser: @{callback.from_user.username}\nItem: {item['name']}\nSize: **{item.get('size', 'N/A')}**\nTotal: {order['total']} ETB\n\n📍 **Address:**\n{address}\n\nDeliver and collect cash.",
            reply_markup=cod_verify_kb(order_id), parse_mode="Markdown"
        )
        
        # 2. Update User Message safely
        try:
            await callback.message.edit_caption(
                caption="✅ **Order Confirmed!**\n\nYou chose Cash on Delivery. Please wait for our delivery agent to contact you.", 
                parse_mode="Markdown"
            )
        except Exception:
            try:
                await callback.message.edit_text(
                    "✅ **Order Confirmed!**\n\nYou chose Cash on Delivery. Please wait for our delivery agent to contact you.", 
                    parse_mode="Markdown"
                )
            except Exception:
                pass
                
        await callback.answer("Order placed successfully!")
    except Exception as e:
        print(f"Error in COD: {e}")
        await callback.answer("An error occurred. Please try again.", show_alert=True)

# --- PAY NOW FLOW (FIXED WITH ADDRESS) ---
@router.callback_query(F.data.startswith("checkout_pay_"))
async def checkout_pay(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.split("_")[2]
        
        try:
            await callback.message.edit_caption(
                caption="💳 **Select Payment Method**\n\nPlease choose your bank to see the account details.",
                reply_markup=payment_method_kb(order_id), parse_mode="Markdown"
            )
        except Exception:
            await callback.message.edit_text(
                "💳 **Select Payment Method**\n\nPlease choose your bank to see the account details.",
                reply_markup=payment_method_kb(order_id), parse_mode="Markdown"
            )
            
        await state.update_data(order_id=order_id)
        await state.set_state(OrderState.waiting_screenshot)
        await callback.answer()
    except Exception as e:
        print(f"Error in Pay Now: {e}")
        await callback.answer("An error occurred.", show_alert=True)

@router.callback_query(F.data.startswith("pay_"))
async def select_payment(callback: CallbackQuery, state: FSMContext):
    _, method, order_id = callback.data.split("_", 2)
    account_info = PAYMENT_ACCOUNTS.get(method, "Account info not configured.")
    await update_order_status(order_id, "pending_payment")

    try:
        await callback.message.edit_caption(
            caption=f"💳 **Payment: {method.upper()}**\n\nPlease transfer to:\n`{account_info}`\n\nAfter payment, **send a screenshot** of the receipt here.",
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.edit_text(
            f"💳 **Payment: {method.upper()}**\n\nPlease transfer to:\n`{account_info}`\n\nAfter payment, **send a screenshot** of the receipt here.",
            parse_mode="Markdown"
        )

    await state.update_data(order_id=order_id, method=method)
    await callback.answer()

@router.message(OrderState.waiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    order = await get_order(order_id)
    item = order['items'][0]
    address = order.get('address', 'Not provided')

    await message.bot.send_photo(
        chat_id=OWNER_ID, photo=message.photo[-1].file_id,
        caption=f"🚨 **New Payment Proof** 🚨\nOrder: `{order_id}`\nUser: @{message.from_user.username or message.from_user.id}\nItem: {item['name']} (Size: {item.get('size', 'N/A')})\n\n📍 **Address:**\n{address}\n\nVerify the transaction then click below.",
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
        try:
            await callback.message.edit_text("📭 You have no orders yet.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👗 Browse Dresses", callback_data="menu_browse")]]))
        except Exception:
            pass
        await callback.answer()
        return
        
    text = "📦 **Your Recent Orders:**\n\n"
    for o in orders:
        status_emoji = "⏳" if "pending" in o['status'] else ("✅" if o['status'] == "paid" else ("🚚" if o['status'] == "delivered" else "❌"))
        item = o['items'][0] if o.get('items') else {}
        size_text = f" (Size: {item.get('size')})" if item.get('size') else ""
        text += f"{status_emoji} `{o['_id']}` — {item.get('name', 'Item')}{size_text} — **{o['status'].replace('_', ' ').title()}**\n"
        
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Menu", callback_data="menu_main")]]), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

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
    await message.answer("✅ Description saved. How many items are **In Stock**?")
    await state.set_state(AddProductState.waiting_stock)

@router.message(AddProductState.waiting_stock)
async def add_stock(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        stock = int(message.text)
        await state.update_data(stock=stock)
        await message.answer("✅ Stock saved. Now send the **Available Sizes**.\n\n*(Separate with commas, e.g., `S, M, L, XL` or `38, 40, 42`. Type `None` if it's one size.)*")
        await state.set_state(AddProductState.waiting_sizes)
    except:
        await message.answer("❌ Invalid number. Send the stock quantity again.")

@router.message(AddProductState.waiting_sizes)
async def add_sizes(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    
    if message.text.lower() == 'none':
        sizes_list = []
    else:
        sizes_list = [s.strip().upper() for s in message.text.split(",")]
        
    data = await state.get_data()
    product_id = await add_product(
        name=data['name'], price=data['price'], description=data['desc'], 
        photo_file_id=data['photo'], stock=data['stock'], sizes=sizes_list
    )
    await state.update_data(product_id=product_id, stock=data['stock'], sizes=sizes_list)
    
    sizes_text = ", ".join(sizes_list) if sizes_list else "One Size"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Yes, Post to Channel", callback_data="post_channel")], [InlineKeyboardButton(text="❌ No, Just Save", callback_data="post_cancel")]])
    await message.answer(f"🎉 Product saved! (Sizes: {sizes_text})\n\nDo you want to post this to your Channel now?", reply_markup=kb)
    await state.set_state(AddProductState.confirm_post)

@router.callback_query(F.data == "post_channel", AddProductState.confirm_post)
async def post_to_channel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    data = await state.get_data()
    
    bot_info = await callback.bot.get_me()
    buy_link = f"https://t.me/{bot_info.username}?start=buy_{data['product_id']}"
    
    channel_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛍 Order Now", url=buy_link)]])
    sizes_str = ", ".join(data.get('sizes', [])) if data.get('sizes') else "One Size"
    caption = f"✨ **{data['name']}** ✨\n\n{data['desc']}\n\n📏 **Sizes:** {sizes_str}\n💰 **Price:** {data['price']} ETB\n📦 **Stock:** {data['stock']} items left!\n\n👇 Tap below to order directly."
    
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
        [InlineKeyboardButton(text="📏 Update Sizes", callback_data="edit_sizes")],
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
    elif field == "sizes":
        await callback.message.edit_text("Send the **new Sizes** (separated by commas, e.g., `S, M, L` or `38, 40`):")
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
        elif field == "sizes": val = [s.strip().upper() for s in val.split(",")]
        
        await update_product(data['edit_id'], {field: val})
        await message.answer(f"✅ Product updated! **{field.title()}** is now: `{val}`", parse_mode="Markdown")
    except:
        await message.answer("❌ Invalid value format. Please try again.")
        
    await state.clear()
