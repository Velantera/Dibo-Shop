from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def payment_method_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Telebirr", callback_data=f"pay_telebirr_{order_id}")],
        [InlineKeyboardButton(text="🏦 CBE", callback_data=f"pay_cbe_{order_id}")],
    ])

def admin_verify_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Confirm Payment", callback_data=f"admin_approve_{order_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"admin_reject_{order_id}"),
        ]
    ])

def cod_verify_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Mark as Delivered (Collected Cash)", callback_data=f"admin_delivered_{order_id}")],
        [InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"admin_reject_{order_id}")]
    ])

def delivery_time_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 Day", callback_data=f"deliver_1_{order_id}"),
            InlineKeyboardButton(text="2 Days", callback_data=f"deliver_2_{order_id}"),
            InlineKeyboardButton(text="3 Days", callback_data=f"deliver_3_{order_id}")
        ]
    ])

def complete_order_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Mark as Completed", callback_data=f"admin_complete_{order_id}")]
    ])

def verify_delivery_fee_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Verify Delivery Fee", callback_data=f"verify_fee_{order_id}")],
        [InlineKeyboardButton(text="❌ Reject Order", callback_data=f"reject_fee_{order_id}")]
    ])

# NEW: For Pay Now Item Payment Verification
def pay_now_verify_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 Day", callback_data=f"deliver_1_{order_id}"),
            InlineKeyboardButton(text="2 Days", callback_data=f"deliver_2_{order_id}"),
            InlineKeyboardButton(text="3 Days", callback_data=f"deliver_3_{order_id}")
        ],
        [InlineKeyboardButton(text="❌ Reject Payment", callback_data=f"admin_reject_{order_id}")]
    ])
