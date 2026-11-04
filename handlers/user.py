from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PAYMENT_ACCOUNTS, OWNER_ID, CHANNEL_ID
from database import (
    get_products, get_all_products, get_product, create_order,
    update_order_status, get_user_orders, add_product, update_product, delete_product,
    get_order, update_order_details, increment_stock, decrement_stock
)
from keyboards import payment_method_kb, admin_verify_kb, cod_verify_kb, delivery_time_kb, complete_order_kb
from locales import TEXTS

router = Router()
DELIVERY_FEE = 300
OWNER_PHONE = "+251927982723"

# --- FSM States ---
class OrderState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_address = State()
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

# --- Helper ---
async def get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "en")

# ==========================================
# 1. LANGUAGE SELECTION & START
# ==========================================
@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    
    if user.id != OWNER_ID: 
        display_name = f"@{user.username}" if user.username else f"[{user.id}](tg://user?id={user.id})"
        notify_text = (
            f"🆕 *New User Started the Bot!*\n\n"
            f"👤 *First Name:* {user.first_name}\n"
            f"🔗 *Contact:* {display_name}\n"
            f"🆔 *ID:* `{user.id}`"
        )
        
        reminder_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Send Reminder", callback_data=f"reminder_{user.id}")]
        ])
        
        try:
            await message.bot.send_message(chat_id=OWNER_ID, text=notify_text, reply_markup=reminder_kb, parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to notify owner: {e}")

    lang_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en"),
            InlineKeyboardButton(text="🇪🇹 Afaan Oromoo", callback_data="setlang_om")
        ]
    ])
    
    await message.answer(
        "🌐 Please choose your language.\n\n"
        "🌐 Maaloo Afaan Filadhaa.",
        reply_markup=lang_kb
    )

@router.callback_query(F.data.startswith("setlang_"))
async def set_language(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(lang=lang, first_name=callback.from_user.first_name)
    t = TEXTS[lang]
    
    await callback.message.edit_text(t["welcome"].format(name=callback.from_user.first_name), reply_markup=main_menu_kb(lang))
    await callback.answer()

@router.callback_query(F.data.startswith("reminder_"))
async def send_reminder(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
        
    target_user_id = int(callback.data.split("_")[1])
    
    lang_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en"),
            InlineKeyboardButton(text="🇪🇹 Afaan Oromoo", callback_data="setlang_om")
        ]
    ])
    
    try:
        await callback.bot.send_message(
            chat_id=target_user_id, 
            text="👋 **Reminder!**\n\nPlease choose your language to continue shopping:", 
            reply_markup=lang_kb
        )
        await callback.answer("✅ Reminder sent successfully!", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Failed to send reminder. User might have blocked the bot.", show_alert=True)

@router.callback_query(F.data == "menu_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    
    data = await state.get_data()
    name = data.get("first_name", callback.from_user.first_name)
    
    try:
        await callback.message.edit_text(t["welcome"].format(name=name), reply_markup=main_menu_kb(lang))
    except Exception:
        await callback.message.answer(t["welcome"].format(name=name), reply_markup=main_menu_kb(lang))
    await callback.answer()

@router.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    try:
        await callback.message.edit_text(
            t["help_text"],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")]]),
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await callback.answer()

# ==========================================
# KEYBOARDS
# ==========================================
def main_menu_kb(lang: str):
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t["btn_browse"], callback_data="menu_browse"),
            InlineKeyboardButton(text=t["btn_orders"], callback_data="menu_orders")
        ],
        [
            InlineKeyboardButton(text=t["btn_help"], callback_data="menu_help"),
            InlineKeyboardButton(text=t["btn_join"], url="https://t.me/Dibo_Demo")
        ]
    ])

def checkout_type_kb(order_id: str, lang: str):
    t = TEXTS[lang]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_cod"], callback_data=f"checkout_cod_{order_id}")],
        [InlineKeyboardButton(text=t["btn_pay_now"], callback_data=f"checkout_pay_{order_id}")],
        [InlineKeyboardButton(text=t["btn_cancel_checkout"], callback_data="menu_main")]
    ])

def size_selection_kb(sizes: list, product_id: str, lang: str):
    t = TEXTS[lang]
    buttons = []
    row = []
    for size in sizes:
        row.append(InlineKeyboardButton(text=size, callback_data=f"selectsize_{size}_{product_id}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text=t["btn_cancel"], callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def user_orders_kb(orders: list, lang: str):
    t = TEXTS[lang]
    buttons = []
    for o in orders:
        if o['status'] in ["pending_details", "pending_payment", "cod_pending"]:
            buttons.append([InlineKeyboardButton(text=t["btn_cancel_order"].format(id=str(o['_id'])[-6:]), callback_data=f"cancel_order_{o['_id']}")])
    buttons.append([InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ==========================================
# 2. BROWSE PRODUCTS
# ==========================================
@router.callback_query(F.data == "menu_browse")
async def browse_products(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    products = await get_products()
    if not products:
        try:
            await callback.message.edit_text(t["shop_empty"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")]]))
        except Exception:
            pass
        await callback.answer()
        return
    
    await state.update_data(products=products, current_index=0)
    await show_product(callback, state)

async def show_product(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    data = await state.get_data()
    products = data.get("products", [])
    idx = data.get("current_index", 0)
    p = products[idx]
    
    sizes_text = ", ".join(p.get("sizes", [])) if p.get("sizes") else "One Size"
    total_with_fee = p['price'] + DELIVERY_FEE
    caption = f"👗 **{p['name']}**\n\n{p.get('description', '')}\n\n📏 **Sizes:** {sizes_text}\n💰 **Item Price:** {p['price']} ETB\n🚚 **Delivery:** {DELIVERY_FEE} ETB\n💵 **Total:** {total_with_fee} ETB\n📦 **In Stock:** {p['stock']}"
    
    nav_buttons = []
    if idx > 0: nav_buttons.append(InlineKeyboardButton(text=t["btn_prev"], callback_data="prod_prev"))
    nav_buttons.append(InlineKeyboardButton(text=t["btn_buy"], callback_data=f"prod_buy_{p['_id']}"))
    if idx < len(products) - 1: nav_buttons.append(InlineKeyboardButton(text=t["btn_next"], callback_data="prod_next"))
        
    kb = InlineKeyboardMarkup(inline_keyboard=[nav_buttons, [InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")]])

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
# 3. CHECKOUT FLOW (NAME -> PHONE -> ADDRESS)
# ==========================================
@router.callback_query(F.data.startswith("prod_buy_"))
async def buy_product_inline(callback: CallbackQuery, state: FSMContext):
    product_id = callback.data.split("_")[2]
    await callback.message.delete()
    await show_size_selection(callback.message, product_id, state)

async def show_size_selection(message: Message, product_id: str, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    product = await get_product(product_id)
    if not product or product.get("stock", 0) <= 0:
        return await message.answer(t["out_of_stock"])

    sizes = product.get("sizes", [])
    if not sizes:
        await prompt_for_name(message, product_id, size="One Size", state=state)
        return

    await message.answer(
        t["select_size"].format(name=product['name']),
        reply_markup=size_selection_kb(sizes, product_id, lang)
    )

@router.callback_query(F.data.startswith("selectsize_"))
async def size_selected(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    size = parts[1]
    product_id = parts[2]
    
    await callback.message.delete()
    await prompt_for_name(callback.message, product_id, size, state)
    await callback.answer()

async def prompt_for_name(message: Message, product_id: str, size: str, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    product = await get_product(product_id)
    
    total_with_fee = product["price"] + DELIVERY_FEE
    
    order_id = await create_order(
        user_id=message.chat.id, username=message.from_user.username if hasattr(message, 'from_user') else message.chat.username,
        items=[{"product_id": str(product["_id"]), "name": product["name"], "price": product["price"], "qty": 1, "size": size}],
        total=total_with_fee,
        language=lang
    )

    await state.update_data(order_id=order_id)
    await state.set_state(OrderState.waiting_name)

    await message.answer(t["enter_name"], parse_mode="Markdown")

@router.message(OrderState.waiting_name)
async def receive_name(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    name = message.text.strip()
    if len(name) < 3:
        return await message.answer(t["name_too_short"])
    
    await state.update_data(customer_name=name)
    await message.answer(t["enter_phone"], parse_mode="Markdown")
    await state.set_state(OrderState.waiting_phone)

@router.message(OrderState.waiting_phone)
async def receive_phone(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    phone = message.text.strip()
    if len(phone) < 9:
        return await message.answer(t["invalid_phone"])
    
    await state.update_data(phone_number=phone)
    await message.answer(t["enter_address"], parse_mode="Markdown")
    await state.set_state(OrderState.waiting_address)

@router.message(OrderState.waiting_address)
async def receive_address(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    address = message.text.strip()
    if len(address) < 5:
        return await message.answer(t["invalid_address"])
    
    data = await state.get_data()
    order_id = data.get("order_id")
    name = data.get("customer_name")
    phone = data.get("phone_number")
    
    await update_order_details(order_id, name, phone, address)
    await update_order_status(order_id, "pending_payment")
    
    order = await get_order(order_id)
    item = order['items'][0]
    
    await message.answer(
        t["order_summary"].format(
            name=item['name'], 
            size=item.get('size'), 
            price=item['price'], 
            total=order['total']
        ),
        reply_markup=checkout_type_kb(order_id, lang),
        parse_mode="Markdown"
    )

# --- COD FLOW ---
@router.callback_query(F.data.startswith("checkout_cod_"))
async def checkout_cod(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    try:
        order_id = callback.data.split("_")[2]
        order = await get_order(order_id)
        
        if not order:
            await callback.answer("Order not found.", show_alert=True)
            return

        await update_order_status(order_id, "cod_pending")
        item = order['items'][0]
        
        owner_msg = t["owner_new_order"].format(
            order_id=order_id,
            name=order.get('customer_name'),
            phone=order.get('phone_number'),
            address=order.get('address'),
            item=item['name'],
            size=item.get('size', 'N/A'),
            total=order['total'],
            payment="Cash on Delivery"
        )
        
        await callback.bot.send_message(
            chat_id=OWNER_ID,
            text=owner_msg,
            reply_markup=delivery_time_kb(order_id), 
            parse_mode="Markdown"
        )
        
        try:
            await callback.message.edit_caption(caption=t["cod_confirmed"], parse_mode="Markdown")
        except Exception:
            try:
                await callback.message.edit_text(t["cod_confirmed"], parse_mode="Markdown")
            except Exception:
                pass
                
        await callback.answer("Order placed successfully!")
    except Exception as e:
        print(f"Error in COD: {e}")
        await callback.answer("An error occurred. Please try again.", show_alert=True)

# --- PAY NOW FLOW ---
@router.callback_query(F.data.startswith("checkout_pay_"))
async def checkout_pay(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    try:
        order_id = callback.data.split("_")[2]
        
        try:
            await callback.message.edit_caption(
                caption=t["select_payment"], 
                reply_markup=payment_method_kb(order_id), 
                parse_mode="Markdown"
            )
        except Exception:
            await callback.message.edit_text(
                t["select_payment"], 
                reply_markup=payment_method_kb(order_id), 
                parse_mode="Markdown"
            )
            
        await state.update_data(order_id=order_id)
        await state.set_state(OrderState.waiting_screenshot)
        await callback.answer()
    except Exception as e:
        print(f"Error in Pay Now: {e}")
        await callback.answer("An error occurred.", show_alert=True)

@router.callback_query(F.data.startswith("pay_"))
async def select_payment(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    _, method, order_id = callback.data.split("_", 2)
    account_info = PAYMENT_ACCOUNTS.get(method, "Account info not configured.")
    order = await get_order(order_id)
    await update_order_status(order_id, "pending_payment")

    try:
        await callback.message.edit_caption(
            caption=t["payment_info"].format(
                method=method.upper(), 
                account=account_info,
                total=order['total']
            ), 
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.edit_text(
            t["payment_info"].format(
                method=method.upper(), 
                account=account_info,
                total=order['total']
            ), 
            parse_mode="Markdown"
        )

    await state.update_data(order_id=order_id, method=method)
    await callback.answer()

@router.message(OrderState.waiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    data = await state.get_data()
    order_id = data.get("order_id")
    order = await get_order(order_id)
    item = order['items'][0]

    owner_msg = t["owner_new_order"].format(
        order_id=order_id,
        name=order.get('customer_name'),
        phone=order.get('phone_number'),
        address=order.get('address'),
        item=item['name'],
        size=item.get('size', 'N/A'),
        total=order['total'],
        payment="Pay Now (Verify Screenshot)"
    )

    await message.bot.send_photo(
        chat_id=OWNER_ID, photo=message.photo[-1].file_id,
        caption=owner_msg,
        parse_mode="Markdown", reply_markup=delivery_time_kb(order_id)
    )

    await message.answer(t["screenshot_received"], reply_markup=main_menu_kb(lang))
    await state.clear()

# ==========================================
# 4. MY ORDERS & CANCELLATION
# ==========================================
@router.callback_query(F.data == "menu_orders")
async def my_orders(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    orders = await get_user_orders(callback.from_user.id)
    if not orders:
        try:
            await callback.message.edit_text(t["no_orders"], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["btn_browse"], callback_data="menu_browse")]]))
        except Exception:
            pass
        await callback.answer()
        return
        
    text = t["orders_list"]
    for o in orders:
        status_emoji = "⏳" if "pending" in o['status'] else ("✅" if o['status'] == "paid" else ("🚚" if o['status'] == "delivered" else "❌"))
        item = o['items'][0] if o.get('items') else {}
        size_text = f" (Size: {item.get('size')})" if item.get('size') else ""
        text += f"{status_emoji} `{str(o['_id'])[-6:]}` — {item.get('name', 'Item')}{size_text} — **{o['status'].replace('_', ' ').title()}**\n"
        
    try:
        await callback.message.edit_text(text, reply_markup=user_orders_kb(orders, lang), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    order_id = callback.data.split("_")[2]
    order = await get_order(order_id)
    
    if not order or order['user_id'] != callback.from_user.id:
        return await callback.answer("Order not found.", show_alert=True)
        
    if order['status'] not in ["pending_details", "pending_payment", "cod_pending"]:
        return await callback.answer(t["cannot_cancel"], show_alert=True)

    await update_order_status(order_id, "cancelled")
    for item in order.get("items", []):
        await increment_stock(item["product_id"], item.get("qty", 1))
        
    item_name = order['items'][0]['name']
    await callback.bot.send_message(
        chat_id=OWNER_ID,
        text=f"🚨 **ORDER CANCELLED BY USER** 🚨\n\nOrder: `{order_id}`\nUser: @{callback.from_user.username}\nItem: {item_name}\nThe stock has been returned automatically.",
        parse_mode="Markdown"
    )
        
    await callback.message.edit_text(t["order_cancelled"], reply_markup=main_menu_kb(lang))
    await callback.answer()

# ==========================================
# 5. ADMIN: DELIVERY & COMPLETION HANDLERS
# ==========================================
@router.callback_query(F.data.startswith("deliver_"))
async def set_delivery_time(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
        
    parts = callback.data.split("_")
    days = parts[1]  # 1, 2, or 3
    order_id = parts[2]
    
    order = await get_order(order_id)
    if not order:
        return await callback.answer("Order not found.", show_alert=True)
        
    user_id = order['user_id']
    item = order['items'][0]
    
    # USE THE SAVED LANGUAGE FROM THE ORDER
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    delivery_text = t[f"delivery_time_{days}"]
    
    # Add the Back to Menu button for the user
    user_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")]
    ])
    
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=t["delivery_notified"].format(days=delivery_text, phone=OWNER_PHONE),
            parse_mode="Markdown",
            reply_markup=user_kb # <-- Added the button here
        )
    except Exception as e:
        print(f"Failed to notify user: {e}")

    # Owner message can stay in English so you can read it easily
    t_en = TEXTS["en"]
    owner_msg = t_en["owner_order_updated"].format(
        order_id=order_id,
        name=order.get('customer_name'),
        phone=order.get('phone_number'),
        address=order.get('address'),
        item=item['name'],
        size=item.get('size', 'N/A'),
        total=order['total'],
        payment=order.get('payment_method', 'COD'),
        days=delivery_text
    )
    
    if callback.message.caption:
        await callback.message.edit_caption(
            caption=owner_msg,
            reply_markup=complete_order_kb(order_id),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            text=owner_msg,
            reply_markup=complete_order_kb(order_id),
            parse_mode="Markdown"
        )
        
    await callback.answer(f"Delivery set to {days} day(s).")

@router.callback_query(F.data.startswith("admin_complete_"))
async def complete_order(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
        
    order_id = callback.data.split("_")[2]
    order = await get_order(order_id)
    
    if not order:
        return await callback.answer("Order not found.", show_alert=True)
        
    await update_order_status(order_id, "delivered")
    
    for item in order.get("items", []):
        await decrement_stock(item["product_id"], item.get("qty", 1))
        
    user_id = order['user_id']
    
    # USE THE SAVED LANGUAGE FROM THE ORDER
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    
    # Add the Back to Menu button for the user
    user_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")]
    ])
    
    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=t["order_completed"],
            parse_mode="Markdown",
            reply_markup=user_kb # <-- Added the button here
        )
    except Exception as e:
        print(f"Failed to notify user: {e}")
        
    if callback.message.caption:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ **COMPLETED**",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            text=callback.message.text + "\n\n✅ **COMPLETED**",
            parse_mode="Markdown"
        )
        
    await callback.answer("Order marked as completed!")

# ==========================================
# 6. ADMIN: ADD PRODUCT (OWNER ONLY)
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
        await message.answer("✅ Stock saved. Now send the **Available Sizes**.\n\n*(Separate with commas, e.g., `S, M, L`. Type `None` if it's one size.)*")
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
    
    channel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Order Now", url=buy_link)]
    ])
    
    sizes_str = ", ".join(data.get('sizes', [])) if data.get('sizes') else "One Size"
    total_with_fee = data['price'] + DELIVERY_FEE
    caption = f"✨ **{data['name']}** ✨\n\n{data['desc']}\n\n📏 **Sizes:** {sizes_str}\n💰 **Item Price:** {data['price']} ETB\n🚚 **Delivery:** {DELIVERY_FEE} ETB\n💵 **Total:** {total_with_fee} ETB\n📦 **Stock:** {data['stock']} items left!\n\n👇 Tap below to order directly."
    
    try:
        if CHANNEL_ID != 0:
            msg = await callback.bot.send_photo(chat_id=CHANNEL_ID, photo=data['photo'], caption=caption, reply_markup=channel_kb, parse_mode="Markdown")
            await update_product(data['product_id'], {"channel_message_id": msg.message_id})
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
# 7. ADMIN: EDIT & DELETE PRODUCT (OWNER ONLY)
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
    product_id = data['edit_id']
    product = await get_product(product_id)
    
    if product and product.get("channel_message_id"):
        try:
            await callback.bot.delete_message(chat_id=CHANNEL_ID, message_id=product["channel_message_id"])
        except Exception as e:
            print(f"Could not delete channel message: {e}")

    await delete_product(product_id)
    await callback.message.edit_text("🗑 **Product Deleted Successfully.** (Removed from Bot and Channel).")
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("edit_"), EditProductState.waiting_action)
async def edit_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[1]
    await state.update_data(edit_field=field)
    
    if field == "photo":
        await callback.message.edit_text("📸 Send the **new Photo** for this product:")
    elif field == "sizes":
        await callback.message.edit_text("Send the **new Sizes** (separated by commas, e.g., `S, M, L`):")
    else:
        await callback.message.edit_text(f"Send the **new {field.title()}** value:")
        
    await state.set_state(EditProductState.waiting_value)
    await callback.answer()

@router.message(EditProductState.waiting_value, F.photo)
async def edit_photo_value(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    product_id = data['edit_id']
    product = await get_product(product_id)
    
    if data['edit_field'] == "photo":
        new_photo = message.photo[-1].file_id
        await update_product(product_id, {"photo_file_id": new_photo})
        
        if product and product.get("channel_message_id"):
            try:
                await message.bot.delete_message(chat_id=CHANNEL_ID, message_id=product["channel_message_id"])
                
                bot_info = await message.bot.get_me()
                buy_link = f"https://t.me/{bot_info.username}?start=buy_{product_id}"
                
                channel_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛍 Order Now", url=buy_link)]
                ])
                
                sizes_str = ", ".join(product.get('sizes', [])) if product.get('sizes') else "One Size"
                total_with_fee = product['price'] + DELIVERY_FEE
                caption = f"✨ **{product['name']}** ✨\n\n{product['description']}\n\n📏 **Sizes:** {sizes_str}\n💰 **Item Price:** {product['price']} ETB\n🚚 **Delivery:** {DELIVERY_FEE} ETB\n💵 **Total:** {total_with_fee} ETB\n📦 **Stock:** {product['stock']} items left!\n\n👇 Tap below to order directly."
                
                msg = await message.bot.send_photo(chat_id=CHANNEL_ID, photo=new_photo, caption=caption, reply_markup=channel_kb, parse_mode="Markdown")
                await update_product(product_id, {"channel_message_id": msg.message_id})
            except Exception as e:
                print(f"Failed to update channel photo: {e}")

        await message.answer("✅ Product photo updated successfully! (Channel updated too)")
        await state.clear()
    else:
        await message.answer("❌ Please send text, not a photo.")

@router.message(EditProductState.waiting_value)
async def edit_text_value(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    field = data['edit_field']
    product_id = data['edit_id']
    
    if field == "photo":
        return await message.answer("❌ Please send a photo, not text.")
        
    val = message.text.strip()
    
    try:
        if field == "price": val = float(val)
        elif field == "stock": val = int(val)
        elif field == "sizes": val = [s.strip().upper() for s in val.split(",")]
        
        await update_product(product_id, {field: val})
        
        product = await get_product(product_id)
        if product and product.get("channel_message_id"):
            try:
                sizes_str = ", ".join(product.get('sizes', [])) if product.get('sizes') else "One Size"
                total_with_fee = product['price'] + DELIVERY_FEE
                caption = f"✨ **{product['name']}** ✨\n\n{product['description']}\n\n📏 **Sizes:** {sizes_str}\n💰 **Item Price:** {product['price']} ETB\n🚚 **Delivery:** {DELIVERY_FEE} ETB\n💵 **Total:** {total_with_fee} ETB\n📦 **Stock:** {product['stock']} items left!\n\n👇 Tap below to order directly."
                
                bot_info = await message.bot.get_me()
                buy_link = f"https://t.me/{bot_info.username}?start=buy_{product_id}"
                
                channel_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛍 Order Now", url=buy_link)]
                ])
                
                await message.bot.edit_message_caption(
                    chat_id=CHANNEL_ID,
                    message_id=product["channel_message_id"],
                    caption=caption,
                    reply_markup=channel_kb,
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Failed to edit channel post: {e} (Message might be identical)")

        await message.answer(f"✅ Product updated! **{field.title()}** is now: `{val}` (Channel updated)", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Invalid format or error: {e}. Please try again.")
        
    await state.clear()

# ==========================================
# 8. CATCH-ALL HANDLER (Fallback for random text)
# ==========================================
@router.message(F.text)
async def catch_all_text(message: Message, state: FSMContext):
    await state.clear()
    
    lang_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en"),
            InlineKeyboardButton(text="🇪🇹 Afaan Oromoo", callback_data="setlang_om")
        ]
    ])
    
    await message.answer(
        "🌐 Please choose your language.\n\n"
        "🌐 Maaloo Afaan Filadhaa.",
        reply_markup=lang_kb
    )
