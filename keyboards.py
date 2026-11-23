from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def payment_method_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Telebirr", callback_data=f"pay_telebirr_{order_id}")],
        [InlineKeyboardButton(text="🏦 CBE", callback_data=f"pay_cbe_{order_id}")],
    ])


def admin_verify_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"admin_approve_{order_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"admin_reject_{order_id}"),
    ]])


def pay_now_verify_kb(order_id: str):
    return admin_verify_kb(order_id)


def cod_verify_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 Day", callback_data=f"deliver_1_{order_id}"),
            InlineKeyboardButton(text="2 Days", callback_data=f"deliver_2_{order_id}"),
            InlineKeyboardButton(text="3 Days", callback_data=f"deliver_3_{order_id}"),
        ],
        [InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"admin_cancel_{order_id}")],
    ])


def delivery_time_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="1 Day", callback_data=f"deliver_1_{order_id}"),
        InlineKeyboardButton(text="2 Days", callback_data=f"deliver_2_{order_id}"),
        InlineKeyboardButton(text="3 Days", callback_data=f"deliver_3_{order_id}"),
    ]])


def complete_order_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Mark as Complete", callback_data=f"admin_complete_{order_id}")],
        [InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"admin_cancel_{order_id}")],
    ])


def verify_delivery_fee_kb(order_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"verify_fee_{order_id}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_fee_{order_id}"),
    ]])


def admin_orders_kb(orders: list):
    buttons = []

    for order in orders:
        order_id = str(order["_id"])
        status = order.get("status", "unknown")

        status_labels = {
            "pending_delivery_fee": "Fee Review",
            "delivery_fee_paid": "Fee Paid",
            "pending_payment": "Payment Review",
            "paid": "Paid",
            "cod_pending": "Cash",
            "delivered": "Completed",
            "cancelled": "Cancelled",
            "rejected": "Rejected",
            "payment_rejected": "Payment Rejected",
            "cancelled_after_fee": "Cancelled (Fee Paid)",
        }
        label_status = status_labels.get(status, status.replace("_", " ").title())

        total = float(order.get("total", 0) or 0)
        fee_paid = (
            status in {
                "delivery_fee_paid", "pending_payment", "paid", "cod_pending",
                "delivered", "payment_rejected", "cancelled_after_fee",
            }
            or bool(order.get("delivery_fee_paid"))
        )
        amount = max(total - 300, 0) if fee_paid else total

        customer_name = (order.get("customer_name") or "Customer").strip()
        if not customer_name:
            customer_name = "Customer"

        buttons.append([InlineKeyboardButton(
            text=f"{customer_name} · {label_status} · {amount:g} ETB",
            callback_data=f"admin_view_order_{order_id}"
        )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_back_orders_kb(order_id: str = None, status: str = ""):
    buttons = []
    terminal_statuses = {"delivered", "cancelled", "rejected", "payment_rejected", "cancelled_after_fee"}

    if order_id and status not in terminal_statuses:
        buttons.append([InlineKeyboardButton(text="✅ Mark as Complete", callback_data=f"admin_complete_{order_id}")])
        buttons.append([InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"admin_cancel_{order_id}")])

    buttons.append([InlineKeyboardButton(text="🔙 Back to Orders", callback_data="admin_all_orders")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _confirmation(order_id: str, yes_text: str, action: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=yes_text, callback_data=f"confirm_{action}_{order_id}")],
        [InlineKeyboardButton(text="↩️ No, Go Back", callback_data=f"admin_view_order_{order_id}")],
    ])


def confirm_approve_kb(order_id: str):
    return _confirmation(order_id, "✅ YES", "approve")


def confirm_reject_kb(order_id: str):
    return _confirmation(order_id, "❌ YES", "reject")


def confirm_complete_kb(order_id: str):
    return _confirmation(order_id, "✅ YES", "complete")


def confirm_cancel_kb(order_id: str):
    return _confirmation(order_id, "❌ YES", "cancel")


def confirm_verify_fee_kb(order_id: str):
    return _confirmation(order_id, "✅ YES", "verify_fee")


def confirm_reject_fee_kb(order_id: str):
    return _confirmation(order_id, "❌ YES", "reject_fee")
