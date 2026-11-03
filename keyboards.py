from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def payment_method_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Telebirr", callback_data=f"pay_telebirr_{order_id}")],
        [InlineKeyboardButton(text="🏦 CBE", callback_data=f"pay_cbe_{order_id}")],
        [InlineKeyboardButton(text="🏦 Awash", callback_data=f"pay_awash_{order_id}")],
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
