from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import PAYMENT_ACCOUNTS, OWNER_ID, OWNER2_ID, OWNER_IDS, CHANNEL_ID, is_admin
from database import (
    get_products, get_all_products, get_product, create_order,
    update_order_status, get_user_orders, add_product, update_product, delete_product,
    get_order, update_order_details, decrement_stock,
    get_all_orders, save_user, update_payment_method  # <-- IMPORTED HERE
)
from keyboards import (
    payment_method_kb, admin_verify_kb, cod_verify_kb, 
    delivery_time_kb, complete_order_kb, verify_delivery_fee_kb, pay_now_verify_kb,
    admin_orders_kb, admin_back_orders_kb,
    confirm_approve_kb, confirm_reject_kb, confirm_complete_kb,
    confirm_cancel_kb, confirm_verify_fee_kb, confirm_reject_fee_kb
)
from locales import TEXTS
from datetime import datetime, timezone, timedelta

router = Router()
DELIVERY_FEE = 300
OWNER_PHONE = "+251927982723"
SHOP_ADDRESS = "📍 **Address:** Addis Ababa, Addis Ketema, Burchuko Condominium, Block - 41, 3rd Floor"

# --- FSM States ---
class OrderState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_address = State()
    waiting_delivery_fee_screenshot = State()
    waiting_final_screenshot = State()

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


DELIVERY_FEE_PAID_STATUSES = {"delivery_fee_paid", "pending_payment", "paid", "cod_pending", "delivered", "payment_rejected", "cancelled_after_fee"}
TERMINAL_ORDER_STATUSES = {"delivered", "cancelled", "rejected", "payment_rejected", "cancelled_after_fee"}


def order_payment_summary(order: dict) -> tuple[float, float, bool]:
    """Return (order_total, remaining_due, delivery_fee_verified)."""
    total = float(order.get("total", 0) or 0)
    fee_paid = order.get("status") in DELIVERY_FEE_PAID_STATUSES or bool(order.get("delivery_fee_paid"))
    remaining = max(total - DELIVERY_FEE, 0) if fee_paid else total
    return total, remaining, fee_paid


async def edit_admin_message(message: Message, text: str, reply_markup=None):
    """Edit either a photo caption or a normal text message."""
    try:
        if message.caption is not None:
            await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception:
        # If Telegram refuses to edit (for example, unchanged content), send a new message.
        await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")


async def ask_owner_confirmation(callback: CallbackQuery, order_id: str, action: str):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ You are not the owner.", show_alert=True)

    order = await get_order(order_id)
    if not order:
        return await callback.answer("Order not found.", show_alert=True)

    prompts = {
        "approve": ("⚠️ **Are you sure you want to APPROVE this payment?**", confirm_approve_kb(order_id)),
        "reject": ("⚠️ **Are you sure you want to REJECT this payment/order?**", confirm_reject_kb(order_id)),
        "complete": ("⚠️ **Are you sure you want to MARK THIS ORDER AS COMPLETE?**", confirm_complete_kb(order_id)),
        "cancel": ("⚠️ **Are you sure you want to CANCEL this order?**", confirm_cancel_kb(order_id)),
        "verify_fee": ("⚠️ **Are you sure the delivery-fee payment is valid and you want to VERIFY it?**", confirm_verify_fee_kb(order_id)),
        "reject_fee": ("⚠️ **Are you sure you want to REJECT the delivery-fee payment?**", confirm_reject_fee_kb(order_id)),
    }
    prompt, keyboard = prompts[action]
    original = callback.message.caption if callback.message.caption is not None else (callback.message.text or "")
    await edit_admin_message(callback.message, f"{original}\n\n{prompt}", keyboard)
    await callback.answer()

# ==========================================
# 1. LANGUAGE SELECTION & START
# ==========================================
@router.message(F.text.startswith("/start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    
    username = user.username if user.username else ""
    await save_user(user.id, user.first_name, username)

    if is_admin(user.id):
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 All Orders", callback_data="admin_all_orders")],
            [
                InlineKeyboardButton(text="➕ Add New Product", callback_data="admin_add_product"),
                InlineKeyboardButton(text="📝 Edit Products", callback_data="admin_edit_products")
            ],
            [InlineKeyboardButton(text="📢 Broadcast Message (Coming Soon)", callback_data="admin_broadcast")]
        ])
        await message.answer(
            "👑 **Owner Dashboard**\n\nManage your shop below:",
            reply_markup=admin_kb,
            parse_mode="Markdown"
        )
        return

    display_name = f"@{user.username}" if user.username else f"[{user.id}](tg://user?id={user.id})"
    notify_text = (
        f"🆕 *New User Started the Bot!*\n\n"
        f"👤 *First Name:* {user.first_name}\n"
        f"🔗 *Contact:* {display_name}\n"
        f"🆔 *ID:* `{user.id}`"
    )
    
    owner_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 All Orders", callback_data="admin_all_orders")],
        [InlineKeyboardButton(text="🔔 Send Reminder", callback_data=f"reminder_{user.id}")]
    ])
    
    for admin_id in OWNER_IDS:
        try:
            await message.bot.send_message(chat_id=admin_id, text=notify_text, reply_markup=owner_kb, parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("buy_"):
        product_id = args[1].replace("buy_", "")
        await state.update_data(deep_link_product=product_id)

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
    
    data = await state.get_data()
    deep_link_product = data.get("deep_link_product")
    
    if deep_link_product:
        await callback.message.delete()
        await show_size_selection(callback.message, deep_link_product, state)
    else:
        await callback.message.edit_text(
            t["welcome"].format(name=callback.from_user.first_name), 
            reply_markup=main_menu_kb(lang)
        )
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def cb_broadcast(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
    await callback.answer("🚧 Broadcast feature is coming soon! You will be able to send messages to all users here.", show_alert=True)

@router.callback_query(F.data.startswith("reminder_"))
async def send_reminder(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
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
    await state.clear()
    
    lang_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="setlang_en"),
            InlineKeyboardButton(text="🇪🇹 Afaan Oromoo", callback_data="setlang_om")
        ]
    ])
    
    try:
        await callback.message.edit_text(
            "🌐 Please choose your language.\n\n"
            "🌐 Maaloo Afaan Filadhaa.",
            reply_markup=lang_kb
        )
    except Exception:
        await callback.message.answer(
            "🌐 Please choose your language.\n\n"
            "🌐 Maaloo Afaan Filadhaa.",
            reply_markup=lang_kb
        )
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
    for idx, size in enumerate(sizes):
        button_text = size.split("|")[0].strip() if "|" in size else size
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=f"selectsize_{idx}_{product_id}")])
    
    buttons.append([InlineKeyboardButton(text=t["btn_cancel"], callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def user_orders_kb(orders: list, lang: str):
    t = TEXTS[lang]
    buttons = []
    for o in orders:
        if o['status'] in ["pending_details", "pending_payment", "cod_pending", "pending_delivery_fee", "delivery_fee_paid"]:
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
    size_index = int(parts[1])
    product_id = parts[2]
    
    product = await get_product(product_id)
    if not product:
        return await callback.answer("Product not found.", show_alert=True)
        
    sizes = product.get("sizes", [])
    if size_index >= len(sizes):
        return await callback.answer("Invalid size selection.", show_alert=True)
        
    raw_size = sizes[size_index]
    
    if "|" in raw_size:
        size_text = raw_size.split("|")[1].strip()
    else:
        size_text = raw_size
    
    await callback.message.delete()
    await prompt_for_name(callback.message, product_id, size_text, state)
    await callback.answer()

async def prompt_for_name(message: Message, product_id: str, size: str, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    product = await get_product(product_id)
    
    await state.update_data(
        product_id=str(product["_id"]),
        product_name=product["name"],
        product_price=product["price"],
        selected_size=size
    )
    
    await state.set_state(OrderState.waiting_name)
    await message.answer(t["enter_name"], parse_mode="Markdown")

@router.message(OrderState.waiting_name)
async def receive_name(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    name = message.text.strip()
    
    if len(name.split()) < 2:
        return await message.answer(t["invalid_name"])
    
    await state.update_data(customer_name=name)
    await message.answer(t["enter_phone"], parse_mode="Markdown")
    await state.set_state(OrderState.waiting_phone)

@router.message(OrderState.waiting_phone)
async def receive_phone(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    phone = message.text.strip()
    
    if not phone.isdigit() or len(phone) != 10 or not phone.startswith("09"):
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
    
    await state.update_data(customer_address=address)
    
    await message.answer(
        t["pay_delivery_first"],
        parse_mode="Markdown"
    )
    await state.set_state(OrderState.waiting_delivery_fee_screenshot)

# --- DELIVERY FEE SCREENSHOT FLOW ---
@router.message(OrderState.waiting_delivery_fee_screenshot, F.photo)
async def receive_delivery_fee_screenshot(message: Message, state: FSMContext):
    lang = await get_lang(state)
    t = TEXTS[lang]
    data = await state.get_data()
    
    total_with_fee = data["product_price"] + DELIVERY_FEE
    
    username = message.from_user.username if message.from_user.username else message.chat.id

    order_id = await create_order(
        user_id=message.chat.id, username=str(username),
        items=[{"product_id": data["product_id"], "name": data["product_name"], "price": data["product_price"], "qty": 1, "size": data["selected_size"]}],
        total=total_with_fee,
        language=lang
    )
    
    await update_order_details(order_id, data["customer_name"], data["phone_number"], data["customer_address"])
    await update_order_status(order_id, "pending_delivery_fee")
    
    order = await get_order(order_id)
    
    for admin_id in OWNER_IDS:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=t["owner_delivery_proof"].format(
                    order_id=order_id,
                    name=order.get('customer_name'),
                    phone=order.get('phone_number'),
                    username=username
                ),
                parse_mode="Markdown",
                reply_markup=verify_delivery_fee_kb(order_id)
            )
        except Exception as e:
            print(f"Failed to send delivery-fee proof to admin {admin_id}: {e}")
    
    await message.answer(t["delivery_fee_proof_sent"], reply_markup=main_menu_kb(lang))
    await state.clear()

# --- OWNER VERIFIES DELIVERY FEE ---
@router.callback_query(F.data.startswith("verify_fee_"))
async def verify_delivery_fee(callback: CallbackQuery):
    order_id = callback.data.removeprefix("verify_fee_")
    order = await get_order(order_id)
    if not order or order.get("status") != "pending_delivery_fee":
        return await callback.answer("This fee is already verified or processed.", show_alert=True)
    await ask_owner_confirmation(callback, order_id, "verify_fee")


@router.callback_query(F.data.startswith("reject_fee_"))
async def reject_delivery_fee(callback: CallbackQuery):
    order_id = callback.data.removeprefix("reject_fee_")
    order = await get_order(order_id)
    if not order or order.get("status") != "pending_delivery_fee":
        return await callback.answer("This order is already processed.", show_alert=True)
    await ask_owner_confirmation(callback, order_id, "reject_fee")


# --- COD FLOW ---
@router.callback_query(F.data.startswith("checkout_cod_"))
async def checkout_cod(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.split("_")[2]
        order = await get_order(order_id)
        
        lang = order.get('language', 'en')
        t = TEXTS[lang]
        
        await update_order_status(order_id, "cod_pending")
        item = order['items'][0]
        
        owner_msg = t["owner_new_order"].format(
            order_id=order_id,
            name=order.get('customer_name'),
            phone=order.get('phone_number'),
            address=order.get('address'),
            item=item['name'],
            size=item.get('size', 'N/A'),
            item_price=item['price'],
            delivery_fee=DELIVERY_FEE,
            remaining=order['total'] - DELIVERY_FEE,
            payment="Cash on Delivery"
        )
        
        for admin_id in OWNER_IDS:
            try:
                await callback.bot.send_message(
                    chat_id=admin_id,
                    text=owner_msg,
                    reply_markup=delivery_time_kb(order_id),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Failed to notify admin {admin_id}: {e}")
        
        user_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")]
        ])
        
        try:
            await callback.message.edit_caption(
                caption=t["cod_confirmed"].format(phone=OWNER_PHONE), 
                parse_mode="Markdown",
                reply_markup=user_kb
            )
        except Exception:
            await callback.message.edit_text(
                t["cod_confirmed"].format(phone=OWNER_PHONE), 
                parse_mode="Markdown",
                reply_markup=user_kb
            )
                
        await callback.answer("Order placed successfully!")
    except Exception as e:
        print(f"Error in COD: {e}")
        await callback.answer("An error occurred. Please try again.", show_alert=True)

# --- PAY NOW FLOW ---
@router.callback_query(F.data.startswith("checkout_pay_"))
async def checkout_pay(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = callback.data.split("_")[2]
        order = await get_order(order_id)
        
        lang = order.get('language', 'en')
        t = TEXTS[lang]
        
        remaining_balance = order['total'] - DELIVERY_FEE
        
        try:
            await callback.message.edit_caption(
                caption=t["select_payment"].format(remaining=remaining_balance), 
                reply_markup=payment_method_kb(order_id), 
                parse_mode="Markdown"
            )
        except Exception:
            await callback.message.edit_text(
                t["select_payment"].format(remaining=remaining_balance), 
                reply_markup=payment_method_kb(order_id), 
                parse_mode="Markdown"
            )
            
        await state.update_data(order_id=order_id)
        await state.set_state(OrderState.waiting_final_screenshot)
        await callback.answer()
    except Exception as e:
        print(f"Error in Pay Now: {e}")
        await callback.answer("An error occurred.", show_alert=True)

@router.callback_query(F.data.startswith("pay_"))
async def select_payment(callback: CallbackQuery, state: FSMContext):
    _, method, order_id = callback.data.split("_", 2)
    order = await get_order(order_id)
    
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    
    account_info = PAYMENT_ACCOUNTS.get(method, "Account info not configured.")
    
    remaining_balance = order['total'] - DELIVERY_FEE
    
    # FIX: Update BOTH the status AND the payment_method in the database!
    await update_order_status(order_id, "pending_payment")
    await update_payment_method(order_id, method) 

    try:
        await callback.message.edit_caption(
            caption=t["payment_info"].format(
                method=method.upper(), 
                account=account_info,
                total=remaining_balance
            ), 
            parse_mode="Markdown"
        )
    except Exception:
        await callback.message.edit_text(
            t["payment_info"].format(
                method=method.upper(), 
                account=account_info,
                total=remaining_balance
            ), 
            parse_mode="Markdown"
        )

    await state.update_data(order_id=order_id, method=method)
    await callback.answer()

@router.message(OrderState.waiting_final_screenshot, F.photo)
async def receive_final_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    order = await get_order(order_id)
    
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    
    item = order['items'][0]

    owner_msg = t["owner_pay_now_proof"].format(
        order_id=order_id,
        name=order.get('customer_name'),
        phone=order.get('phone_number'),
        address=order.get('address'),
        item=item['name'],
        size=item.get('size', 'N/A'),
        item_price=item['price'],
        delivery_fee=DELIVERY_FEE,
        remaining=order['total'] - DELIVERY_FEE,
        payment="Pay Now (Item Verified)"
    )

    for admin_id in OWNER_IDS:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=message.photo[-1].file_id,
                caption=owner_msg,
                parse_mode="Markdown",
                reply_markup=admin_verify_kb(order_id)
            )
        except Exception as e:
            print(f"Failed to send final payment proof to admin {admin_id}: {e}")

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
        
        display_status = o['status']
        if o.get('payment_method') in ['telebirr', 'cbe'] and o['status'] in ['pending_payment', 'paid']:
            display_status = "Paid"
        elif o['status'] == 'cod_pending':
            display_status = "Cash"
        else:
            display_status = display_status.replace('_', ' ').title()
        
        _, remaining_due, fee_paid = order_payment_summary(o)
        due_label = "Remaining" if fee_paid else "Total due"
        text += f"{status_emoji} `{str(o['_id'])[-6:]}` — {item.get('name', 'Item')}{size_text} — **{display_status}**\n   {due_label}: {remaining_due:g} ETB\n"
        
    try:
        await callback.message.edit_text(text, reply_markup=user_orders_kb(orders, lang), parse_mode="Markdown")
    except Exception:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    order_id = callback.data.split("_")[2]
    order = await get_order(order_id)
    
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    
    if not order or order['user_id'] != callback.from_user.id:
        return await callback.answer("Order not found.", show_alert=True)
        
    if order['status'] not in ["pending_details", "pending_payment", "cod_pending", "pending_delivery_fee", "delivery_fee_paid"]:
        return await callback.answer(t["cannot_cancel"], show_alert=True)

    order_time = order.get('created_at')
    if order_time:
        now = datetime.now(timezone.utc)
        if order_time.tzinfo is None:
            order_time = order_time.replace(tzinfo=timezone.utc)
            
        if now - order_time > timedelta(hours=24):
            return await callback.answer(t["cannot_cancel_24h"], show_alert=True)

    cancellation_status = "cancelled_after_fee" if order.get("status") in DELIVERY_FEE_PAID_STATUSES else "cancelled"
    await update_order_status(order_id, cancellation_status)
    # Stock is deducted only when an order is completed, so do not increment it here.
    item_name = order['items'][0]['name']
    
    cancel_msg = t["owner_cancel_notice"].format(
        order_id=order_id,
        name=order.get('customer_name'),
        phone=order.get('phone_number'),
        address=order.get('address'),
        item=item_name
    )
    
    for admin_id in OWNER_IDS:
        try:
            await callback.bot.send_message(
                chat_id=admin_id,
                text=cancel_msg,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to send cancellation notice to admin {admin_id}: {e}")
        
    await callback.message.edit_text(t["order_cancelled"], reply_markup=main_menu_kb(lang))
    await callback.answer()

# ==========================================
# 5. ADMIN: DELIVERY & COMPLETION HANDLERS
# ==========================================
DELIVERY_ELIGIBLE_STATUSES = {"paid", "cod_pending"}


@router.callback_query(F.data.startswith("deliver_"))
async def set_delivery_time(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    parts = callback.data.split("_", 2)
    if len(parts) != 3 or parts[1] not in {"1", "2", "3"}:
        return await callback.answer("Invalid delivery selection.", show_alert=True)

    days, order_id = parts[1], parts[2]
    order = await get_order(order_id)
    if not order:
        return await callback.answer("Order not found.", show_alert=True)
    if order.get("status") not in DELIVERY_ELIGIBLE_STATUSES:
        return await callback.answer("Approve payment or confirm COD before setting delivery.", show_alert=True)

    user_id = order["user_id"]
    lang = order.get("language", "en")
    t = TEXTS.get(lang, TEXTS["en"])
    delivery_text = t.get(f"delivery_time_{days}", f"{days} day(s)")
    user_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t.get("btn_main_menu", "Main Menu"), callback_data="menu_main")
    ]])

    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=t.get("delivery_notified", "Your order is expected to arrive in {days}. Contact {phone}.").format(
                days=delivery_text, phone=OWNER_PHONE
            ),
            parse_mode="Markdown",
            reply_markup=user_kb
        )
    except Exception as e:
        print(f"Failed to notify customer about delivery time: {e}")

    item = order.get("items", [{}])[0]
    owner_msg = TEXTS["en"].get(
        "owner_order_updated",
        "Order {order_id} updated\nCustomer: {name}\nPhone: {phone}\nAddress: {address}\nItem: {item}\nSize: {size}\nRemaining: {remaining} ETB\nPayment: {payment}\nDelivery: {days}"
    ).format(
        order_id=order_id,
        name=order.get("customer_name", "N/A"),
        phone=order.get("phone_number", "N/A"),
        address=order.get("address", "N/A"),
        item=item.get("name", "N/A"),
        size=item.get("size", "N/A"),
        remaining=order_payment_summary(order)[1],
        payment=order.get("payment_method") or "COD",
        days=delivery_text
    )

    await edit_admin_message(callback.message, owner_msg, complete_order_kb(order_id))
    await callback.answer(f"Delivery set to {days} day(s).")


@router.callback_query(F.data.startswith("admin_approve_"))
async def request_payment_approval(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
    order_id = callback.data.removeprefix("admin_approve_")
    order = await get_order(order_id)
    if not order or order.get("status") != "pending_payment":
        return await callback.answer("This order is not awaiting payment approval.", show_alert=True)
    await ask_owner_confirmation(callback, order_id, "approve")


@router.callback_query(F.data.startswith("admin_reject_"))
async def request_payment_rejection(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
    order_id = callback.data.removeprefix("admin_reject_")
    order = await get_order(order_id)
    if not order or order.get("status") in TERMINAL_ORDER_STATUSES:
        return await callback.answer("This order has already been processed.", show_alert=True)
    await ask_owner_confirmation(callback, order_id, "reject")


@router.callback_query(F.data.startswith("admin_complete_"))
async def request_order_completion(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
    order_id = callback.data.removeprefix("admin_complete_")
    order = await get_order(order_id)
    if not order or order.get("status") in TERMINAL_ORDER_STATUSES:
        return await callback.answer("This order cannot be completed.", show_alert=True)
    if order.get("status") not in DELIVERY_ELIGIBLE_STATUSES:
        return await callback.answer("Approve payment / confirm COD before completing this order.", show_alert=True)
    await ask_owner_confirmation(callback, order_id, "complete")


@router.callback_query(F.data.startswith("admin_cancel_"))
async def request_order_cancellation(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
    order_id = callback.data.removeprefix("admin_cancel_")
    order = await get_order(order_id)
    if not order or order.get("status") in TERMINAL_ORDER_STATUSES:
        return await callback.answer("This order has already been processed.", show_alert=True)
    await ask_owner_confirmation(callback, order_id, "cancel")


@router.callback_query(F.data.startswith("confirm_approve_"))
@router.callback_query(F.data.startswith("confirm_reject_"))
@router.callback_query(F.data.startswith("confirm_complete_"))
@router.callback_query(F.data.startswith("confirm_cancel_"))
@router.callback_query(F.data.startswith("confirm_verify_fee_"))
@router.callback_query(F.data.startswith("confirm_reject_fee_"))
async def process_confirmed_admin_action(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ You are not the owner.", show_alert=True)

    payload = callback.data.removeprefix("confirm_")
    action = None
    order_id = None
    for candidate in ("verify_fee", "reject_fee", "approve", "reject", "complete", "cancel"):
        prefix = candidate + "_"
        if payload.startswith(prefix):
            action = candidate
            order_id = payload[len(prefix):]
            break

    if not action or not order_id:
        return await callback.answer("Invalid confirmation callback.", show_alert=True)

    order = await get_order(order_id)
    if not order:
        return await callback.answer("Order not found.", show_alert=True)

    status = order.get("status")
    user_id = order["user_id"]
    lang = order.get("language", "en")
    t = TEXTS.get(lang, TEXTS["en"])
    items = order.get("items", [])
    item = items[0] if items else {"name": "your item"}

    if action == "approve":
        if status != "pending_payment":
            return await callback.answer("This payment is no longer awaiting approval.", show_alert=True)
        await update_order_status(order_id, "paid")
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=f"🎉 **Payment Confirmed!**\n\nYour payment for order `{order_id}` has been verified successfully. We are preparing your order.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to notify customer about approved payment: {e}")
        result_text = "✅ **PAYMENT APPROVED SUCCESSFULLY**\n\nSelect the estimated delivery time below:"
        result_markup = delivery_time_kb(order_id)

    elif action == "reject":
        if status in TERMINAL_ORDER_STATUSES:
            return await callback.answer("This order has already been processed.", show_alert=True)
        rejection_status = "payment_rejected" if status in DELIVERY_FEE_PAID_STATUSES else "rejected"
        await update_order_status(order_id, rejection_status)
        if order.get("payment_method") in {"telebirr", "cbe"} and status == "pending_payment":
            reject_msg = t.get("owner_pay_now_rejected", "Your payment was rejected. Please contact {phone}.").format(item=item.get("name", "item"), phone=OWNER_PHONE)
        else:
            reject_msg = t.get("order_rejected", "Your order was rejected. Please contact {phone}.").format(phone=OWNER_PHONE)
        try:
            await callback.bot.send_message(chat_id=user_id, text=reject_msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Failed to notify customer about rejection: {e}")
        result_text, result_markup = "❌ **ORDER REJECTED SUCCESSFULLY**", None

    elif action == "verify_fee":
        if status != "pending_delivery_fee":
            return await callback.answer("This delivery fee is no longer awaiting verification.", show_alert=True)
        await update_order_status(order_id, "delivery_fee_paid")
        _, remaining, _ = order_payment_summary({**order, "status": "delivery_fee_paid"})
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=t.get("delivery_verified_msg", "Delivery fee verified. Remaining balance: {remaining} ETB.").format(remaining=remaining),
                reply_markup=checkout_type_kb(order_id, lang),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to notify customer about delivery fee verification: {e}")
        result_text, result_markup = "✅ **DELIVERY FEE VERIFIED SUCCESSFULLY**", None

    elif action == "reject_fee":
        if status != "pending_delivery_fee":
            return await callback.answer("This delivery fee is no longer awaiting verification.", show_alert=True)
        await update_order_status(order_id, "rejected")
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=t.get("order_rejected", "Your order was rejected. Please contact {phone}.").format(phone=OWNER_PHONE),
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to notify customer about rejected delivery fee: {e}")
        result_text, result_markup = "❌ **DELIVERY FEE / ORDER REJECTED**", None

    elif action == "complete":
        if status not in DELIVERY_ELIGIBLE_STATUSES:
            return await callback.answer("This order is not ready to be completed.", show_alert=True)
        await update_order_status(order_id, "delivered")
        for order_item in items:
            await decrement_stock(order_item["product_id"], order_item.get("qty", 1))
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=t.get("order_completed", "Your order has been completed."),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=t.get("btn_main_menu", "Main Menu"), callback_data="menu_main")
                ]])
            )
        except Exception as e:
            print(f"Failed to notify customer about completion: {e}")
        result_text, result_markup = "✅ **ORDER COMPLETED SUCCESSFULLY**", None

    elif action == "cancel":
        if status in TERMINAL_ORDER_STATUSES:
            return await callback.answer("This order has already been processed.", show_alert=True)
        cancellation_status = "cancelled_after_fee" if status in DELIVERY_FEE_PAID_STATUSES else "cancelled"
        await update_order_status(order_id, cancellation_status)
        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=f"❌ **Your order `{order_id}` has been cancelled by the shop owner.**\nPlease contact {OWNER_PHONE} if you have questions.",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to notify customer about cancellation: {e}")
        result_text, result_markup = "❌ **ORDER CANCELLED SUCCESSFULLY**", None

    else:
        return await callback.answer("Unknown action.", show_alert=True)

    await edit_admin_message(callback.message, result_text, result_markup)
    await callback.answer("Action confirmed successfully.")

# ==========================================
# 6. ADMIN: ADD PRODUCT (OWNER ONLY)
# ==========================================
@router.callback_query(F.data == "admin_add_product")
async def cb_addproduct(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
    await callback.message.answer("📸 Send me a **photo** of the dress.")
    await state.set_state(AddProductState.waiting_photo)
    await callback.answer()

@router.message(F.text == "/addproduct")
async def cmd_addproduct(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ You are not authorized to use this command.")
        
    await message.answer("📸 Send me a **photo** of the dress.")
    await state.set_state(AddProductState.waiting_photo)

@router.message(AddProductState.waiting_photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("✅ Photo saved. Now send me the **Name** of the dress.")
    await state.set_state(AddProductState.waiting_name)

@router.message(AddProductState.waiting_name)
async def add_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(name=message.text)
    await message.answer("✅ Name saved. Now send the **Price** (numbers only).")
    await state.set_state(AddProductState.waiting_price)

@router.message(AddProductState.waiting_price)
async def add_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        await state.update_data(price=float(message.text))
        await message.answer("✅ Price saved. Now send a short **Description**.")
        await state.set_state(AddProductState.waiting_desc)
    except:
        await message.answer("❌ Invalid number. Send the price again.")

@router.message(AddProductState.waiting_desc)
async def add_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(desc=message.text)
    await message.answer("✅ Description saved. How many items are **In Stock**?")
    await state.set_state(AddProductState.waiting_stock)

@router.message(AddProductState.waiting_stock)
async def add_stock(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        stock = int(message.text)
        await state.update_data(stock=stock)
        
        lang = await get_lang(state)
        t = TEXTS[lang]
        await message.answer(t["enter_sizes"])
        await state.set_state(AddProductState.waiting_sizes)
    except:
        await message.answer("❌ Invalid number. Send the stock quantity again.")

@router.message(AddProductState.waiting_sizes)
async def add_sizes(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    
    sizes_list = [message.text.strip()]
    
    data = await state.get_data()
    product_id = await add_product(
        name=data['name'], price=data['price'], description=data['desc'], 
        photo_file_id=data['photo'], stock=data['stock'], sizes=sizes_list
    )
    await state.update_data(product_id=product_id, stock=data['stock'], sizes=sizes_list)
    
    sizes_text = sizes_list[0]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Yes, Post to Channel", callback_data="post_channel")], [InlineKeyboardButton(text="❌ No, Just Save", callback_data="post_cancel")]])
    await message.answer(f"🎉 Product saved! (Size: {sizes_text})\n\nDo you want to post this to your Channel now?", reply_markup=kb)
    await state.set_state(AddProductState.confirm_post)

@router.callback_query(F.data == "post_channel", AddProductState.confirm_post)
async def post_to_channel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return
    data = await state.get_data()
    
    bot_info = await callback.bot.get_me()
    buy_link = f"https://t.me/{bot_info.username}?start=buy_{data['product_id']}"
    
    channel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Order Now", url=buy_link)]
    ])
    
    sizes_str = ", ".join(data.get('sizes', [])) if data.get('sizes') else "One Size"
    total_with_fee = data['price'] + DELIVERY_FEE
    caption = f"✨ **{data['name']}** ✨\n\n{data['desc']}\n\n📏 **Sizes:** {sizes_str}\n💰 **Item Price:** {data['price']} ETB\n🚚 **Delivery:** {DELIVERY_FEE} ETB\n💵 **Total:** {total_with_fee} ETB\n📦 **Stock:** {data['stock']} items left!\n\n{SHOP_ADDRESS}\n\n👇 Tap below to order directly."
    
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
    if not is_admin(callback.from_user.id): return
    await callback.message.edit_text("✅ Product saved (not posted).")
    await state.clear()

# ==========================================
# 7. ADMIN: EDIT & DELETE PRODUCT (OWNER ONLY)
# ==========================================
@router.callback_query(F.data == "admin_edit_products")
async def cb_editproduct(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
        
    products = await get_all_products()
    if not products:
        return await callback.message.answer("No products found in DB.")
    
    text = "Send the **Product ID** you want to edit/delete:\n\n"
    for p in products:
        text += f"`{p['_id']}` — {p['name']} (Stock: {p['stock']}, Price: {p['price']})\n"
    
    await callback.message.answer(text, parse_mode="Markdown")
    await state.set_state(EditProductState.waiting_id)
    await callback.answer()

@router.message(F.text == "/editproduct")
async def cmd_editproduct(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
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
    if not is_admin(message.from_user.id): return
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
    if not is_admin(callback.from_user.id): return
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
    if not is_admin(callback.from_user.id): return
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
    if not is_admin(callback.from_user.id): return
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
    if not is_admin(message.from_user.id): return
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
                caption = f"✨ **{product['name']}** ✨\n\n{product['description']}\n\n📏 **Sizes:** {sizes_str}\n💰 **Item Price:** {product['price']} ETB\n🚚 **Delivery:** {DELIVERY_FEE} ETB\n💵 **Total:** {total_with_fee} ETB\n📦 **Stock:** {product['stock']} items left!\n\n{SHOP_ADDRESS}\n\n👇 Tap below to order directly."
                
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
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    field = data['edit_field']
    product_id = data['edit_id']
    
    if field == "photo":
        return await message.answer("❌ Please send a photo, not text.")
        
    val = message.text.strip()
    
    try:
        if field == "price": val = float(val)
        elif field == "stock": val = int(val)
        elif field == "sizes": val = [val]
        
        await update_product(product_id, {field: val})
        
        product = await get_product(product_id)
        if product and product.get("channel_message_id"):
            try:
                sizes_str = ", ".join(product.get('sizes', [])) if product.get('sizes') else "One Size"
                total_with_fee = product['price'] + DELIVERY_FEE
                caption = f"✨ **{product['name']}** ✨\n\n{product['description']}\n\n📏 **Sizes:** {sizes_str}\n💰 **Item Price:** {product['price']} ETB\n🚚 **Delivery:** {DELIVERY_FEE} ETB\n💵 **Total:** {total_with_fee} ETB\n📦 **Stock:** {product['stock']} items left!\n\n{SHOP_ADDRESS}\n\n👇 Tap below to order directly."
                
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
# 8. ADMIN: ALL ORDERS HANDLER
# ==========================================
@router.callback_query(F.data == "admin_all_orders")
async def admin_all_orders(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)
        
    orders = await get_all_orders()
    
    if not orders:
        try:
            await callback.message.edit_text("📭 No orders found.", reply_markup=main_menu_kb("en"))
        except Exception:
            pass
        return await callback.answer()
        
    text = "📋 **All Orders:**\n\nEach order button shows its current amount due. Select an order to view full details."
    kb = admin_orders_kb(orders)
    
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_view_order_"))
async def admin_view_order(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("admin_view_order_")
    order = await get_order(order_id)
    if not order:
        return await callback.answer("Order not found.", show_alert=True)

    item = order.get("items", [{}])[0] if order.get("items") else {}
    status = order.get("status", "Unknown")
    display_status = status.replace("_", " ").title()
    if status == "cod_pending":
        display_status = "Cash on Delivery"
    elif status in {"pending_payment", "paid"} and order.get("payment_method") in ["telebirr", "cbe"]:
        display_status = "Payment Awaiting Approval" if status == "pending_payment" else "Paid"

    total, remaining, fee_paid = order_payment_summary(order)
    delivery_status = "Paid / Verified" if fee_paid else "Not yet verified"
    payment_method = (order.get("payment_method") or "Not selected").replace("_", " ").title()

    text = (
        f"📦 **Order Details**\n\n"
        f"🆔 Order: `{order_id}`\n"
        f"👤 Name: {order.get('customer_name', 'N/A')}\n"
        f"📞 Phone: {order.get('phone_number', 'N/A')}\n"
        f"📍 Address: {order.get('address', 'N/A')}\n\n"
        f"👗 Item: {item.get('name', 'N/A')} (Size: {item.get('size', 'N/A')})\n"
        f"💰 Order Total: {total:g} ETB\n"
        f"🚚 Delivery Fee: {DELIVERY_FEE} ETB ({delivery_status})\n"
        f"💵 **Remaining to Collect: {remaining:g} ETB**\n"
        f"💳 Payment: {payment_method}\n"
        f"📊 Status: {display_status}"
    )

    await edit_admin_message(callback.message, text, admin_back_orders_kb(order_id, status))
    await callback.answer()

# ==========================================
# 9. CATCH-ALL HANDLER (Fallback for random text)
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
