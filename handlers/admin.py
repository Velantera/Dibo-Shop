from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import OWNER_ID
from database import (
    get_order,
    get_all_orders,
    update_order_status,
    update_order_fields,
    decrement_stock,
)
from keyboards import (
    confirm_approve_kb,
    confirm_reject_kb,
    confirm_complete_kb,
    confirm_cancel_kb,
    confirm_verify_fee_kb,
    confirm_reject_fee_kb,
    delivery_time_kb,
    complete_order_kb,
    admin_orders_kb,
    admin_back_orders_kb,
    payment_method_kb,
)
from locales import TEXTS

router = Router()

DELIVERY_FEE = 300
OWNER_PHONE = "+251927982723"

DELIVERY_FEE_PAID_STATUSES = {
    "delivery_fee_paid",
    "pending_payment",
    "paid",
    "cod_pending",
    "delivered",
    "payment_rejected",
    "cancelled_after_fee",
}

TERMINAL_ORDER_STATUSES = {
    "delivered",
    "cancelled",
    "rejected",
    "payment_rejected",
    "cancelled_after_fee",
}


def is_owner(callback: CallbackQuery) -> bool:
    return callback.from_user.id == OWNER_ID


def order_payment_summary(order: dict):
    total = float(order.get("total", 0) or 0)

    fee_paid = (
        order.get("status") in DELIVERY_FEE_PAID_STATUSES
        or bool(order.get("delivery_fee_paid"))
    )

    remaining = max(total - DELIVERY_FEE, 0) if fee_paid else total

    return total, remaining, fee_paid


def get_order_item(order: dict):
    items = order.get("items", [])
    return items[0] if items else {"name": "Item", "size": "N/A"}


async def edit_admin_message(message, text: str, reply_markup=None):
    """Edit either a photo caption or a normal text message."""
    try:
        if message.caption is not None:
            await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        else:
            await message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
    except Exception as e:
        print(f"Could not edit admin message: {e}")
        try:
            await message.answer(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        except Exception as send_error:
            print(f"Could not send replacement admin message: {send_error}")


async def ask_owner_confirmation(
    callback: CallbackQuery,
    order_id: str,
    action: str,
):
    if not is_owner(callback):
        return await callback.answer(
            "⛔ You are not the owner.",
            show_alert=True,
        )

    order = await get_order(order_id)

    if not order:
        return await callback.answer(
            "Order not found.",
            show_alert=True,
        )

    prompts = {
        "approve": (
            "⚠️ **Are you sure you want to APPROVE this payment?**",
            confirm_approve_kb(order_id),
        ),
        "reject": (
            "⚠️ **Are you sure you want to REJECT this payment?**",
            confirm_reject_kb(order_id),
        ),
        "complete": (
            "⚠️ **Are you sure you want to MARK THIS ORDER AS COMPLETE?**",
            confirm_complete_kb(order_id),
        ),
        "cancel": (
            "⚠️ **Are you sure you want to CANCEL this order?**",
            confirm_cancel_kb(order_id),
        ),
        "verify_fee": (
            "⚠️ **Have you confirmed receipt of 300 ETB and do you want to VERIFY this delivery fee?**",
            confirm_verify_fee_kb(order_id),
        ),
        "reject_fee": (
            "⚠️ **Are you sure you want to REJECT this delivery-fee payment?**",
            confirm_reject_fee_kb(order_id),
        ),
    }

    prompt, keyboard = prompts[action]

    original = (
        callback.message.caption
        if callback.message.caption is not None
        else (callback.message.text or "")
    )

    await edit_admin_message(
        callback.message,
        f"{original}\n\n{prompt}",
        keyboard,
    )

    await callback.answer()


# ==================================================
# PAYMENT APPROVAL / REJECTION REQUESTS
# ==================================================

@router.callback_query(F.data.startswith("admin_approve_"))
async def request_payment_approval(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("admin_approve_")
    order = await get_order(order_id)

    if not order or order.get("status") != "pending_payment":
        return await callback.answer(
            "This order is not awaiting payment approval.",
            show_alert=True,
        )

    await ask_owner_confirmation(callback, order_id, "approve")


@router.callback_query(F.data.startswith("admin_reject_"))
async def request_payment_rejection(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("admin_reject_")
    order = await get_order(order_id)

    if not order or order.get("status") in TERMINAL_ORDER_STATUSES:
        return await callback.answer(
            "This order has already been processed.",
            show_alert=True,
        )

    await ask_owner_confirmation(callback, order_id, "reject")


# ==================================================
# DELIVERY FEE CONFIRMATION REQUESTS
# ==================================================

@router.callback_query(F.data.startswith("verify_fee_"))
async def request_delivery_fee_verification(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("verify_fee_")
    order = await get_order(order_id)

    if not order or order.get("status") != "pending_delivery_fee":
        return await callback.answer(
            "This delivery fee is no longer awaiting verification.",
            show_alert=True,
        )

    await ask_owner_confirmation(callback, order_id, "verify_fee")


@router.callback_query(F.data.startswith("reject_fee_"))
async def request_delivery_fee_rejection(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("reject_fee_")
    order = await get_order(order_id)

    if not order or order.get("status") != "pending_delivery_fee":
        return await callback.answer(
            "This delivery fee is no longer awaiting verification.",
            show_alert=True,
        )

    await ask_owner_confirmation(callback, order_id, "reject_fee")


# ==================================================
# COMPLETION / CANCELLATION REQUESTS
# ==================================================

@router.callback_query(F.data.startswith("admin_complete_"))
async def request_order_completion(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("admin_complete_")
    order = await get_order(order_id)

    if not order or order.get("status") in TERMINAL_ORDER_STATUSES:
        return await callback.answer(
            "This order cannot be completed.",
            show_alert=True,
        )

    if order.get("status") not in {
        "paid",
        "cod_pending",
        "delivery_fee_paid",
    }:
        return await callback.answer(
            "This order is not ready to be completed.",
            show_alert=True,
        )

    await ask_owner_confirmation(callback, order_id, "complete")


@router.callback_query(F.data.startswith("admin_cancel_"))
async def request_order_cancellation(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("admin_cancel_")
    order = await get_order(order_id)

    if not order or order.get("status") in TERMINAL_ORDER_STATUSES:
        return await callback.answer(
            "This order has already been processed.",
            show_alert=True,
        )

    await ask_owner_confirmation(callback, order_id, "cancel")


# ==================================================
# CONFIRMATION BUTTONS
# ==================================================

@router.callback_query(F.data.startswith("confirm_"))
async def process_confirmed_admin_action(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer(
            "⛔ You are not the owner.",
            show_alert=True,
        )

    # IMPORTANT:
    # Match complete action prefixes because verify_fee and reject_fee
    # contain underscores.
    payload = callback.data.removeprefix("confirm_")

    action = None
    order_id = None

    for candidate in (
        "verify_fee",
        "reject_fee",
        "approve",
        "reject",
        "complete",
        "cancel",
    ):
        prefix = candidate + "_"

        if payload.startswith(prefix):
            action = candidate
            order_id = payload[len(prefix):]
            break

    if not action or not order_id:
        return await callback.answer(
            "Invalid confirmation callback.",
            show_alert=True,
        )

    order = await get_order(order_id)

    if not order:
        return await callback.answer(
            "Order not found in database.",
            show_alert=True,
        )

    status = order.get("status")
    user_id = order.get("user_id")
    lang = order.get("language", "en")
    t = TEXTS.get(lang, TEXTS["en"])
    item = get_order_item(order)
    items = order.get("items", [])

    # ---------------- APPROVE ITEM PAYMENT ----------------

    if action == "approve":
        if status != "pending_payment":
            return await callback.answer(
                "This payment is no longer awaiting approval.",
                show_alert=True,
            )

        await update_order_status(order_id, "paid")

        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 **Payment Confirmed!**\n"
                    f"Order `{order_id}` is now being processed."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Could not notify customer about approval: {e}")

        # Keep the 1, 2, and 3 day delivery buttons.
        owner_text = (
            f"✅ **PAYMENT APPROVED**\n\n"
            f"🆔 Order: `{order_id}`\n"
            f"👤 Name: {order.get('customer_name', 'N/A')}\n"
            f"📞 Phone: {order.get('phone_number', 'N/A')}\n"
            f"📍 Address: {order.get('address', 'N/A')}\n\n"
            f"👗 Item: {item.get('name', 'Item')} "
            f"(Size: {item.get('size', 'N/A')})\n"
            f"💰 Remaining to Collect: "
            f"{order_payment_summary({**order, 'status': 'paid'})[1]:g} ETB\n\n"
            f"👇 **Select Delivery Time:**"
        )

        await edit_admin_message(
            callback.message,
            owner_text,
            delivery_time_kb(order_id),
        )

        return await callback.answer("Payment approved. Select delivery time.")

    # ---------------- REJECT ITEM PAYMENT ----------------

    elif action == "reject":
        if status != "pending_payment":
            return await callback.answer(
                "This payment is no longer awaiting rejection.",
                show_alert=True,
            )

        await update_order_status(order_id, "payment_rejected")

        try:
            reject_msg = t["owner_pay_now_rejected"].format(
                item=item.get("name", "item"),
                phone=OWNER_PHONE,
            )

            await callback.bot.send_message(
                chat_id=user_id,
                text=reject_msg,
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Could not notify customer about rejection: {e}")

        await edit_admin_message(
            callback.message,
            "❌ **ITEM PAYMENT REJECTED**",
            None,
        )

        return await callback.answer("Payment rejected.")

    # ---------------- VERIFY DELIVERY FEE ----------------

    elif action == "verify_fee":
        if status != "pending_delivery_fee":
            return await callback.answer(
                "This delivery fee is no longer awaiting verification.",
                show_alert=True,
            )

        await update_order_status(order_id, "delivery_fee_paid")

        # Save explicit confirmation as well as the status.
        await update_order_fields(
            order_id,
            {"delivery_fee_paid": True},
        )

        updated_order = {**order, "status": "delivery_fee_paid"}
        _, remaining, _ = order_payment_summary(updated_order)

        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=t["delivery_verified_msg"].format(
                    remaining=remaining
                ),
                reply_markup=payment_method_kb(order_id),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Could not notify customer about fee verification: {e}")

        await edit_admin_message(
            callback.message,
            (
                "✅ **DELIVERY FEE VERIFIED SUCCESSFULLY**\n\n"
                f"Order: `{order_id}`\n"
                f"Delivery fee received: {DELIVERY_FEE} ETB\n"
                f"Remaining item payment: {remaining:g} ETB"
            ),
            None,
        )

        return await callback.answer("Delivery fee verified.")

    # ---------------- REJECT DELIVERY FEE ----------------

    elif action == "reject_fee":
        if status != "pending_delivery_fee":
            return await callback.answer(
                "This delivery fee is no longer awaiting verification.",
                show_alert=True,
            )

        await update_order_status(order_id, "rejected")

        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=t["order_rejected"].format(phone=OWNER_PHONE),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Could not notify customer about rejected fee: {e}")

        await edit_admin_message(
            callback.message,
            "❌ **DELIVERY FEE / ORDER REJECTED**",
            None,
        )

        return await callback.answer("Delivery fee rejected.")

    # ---------------- MARK ORDER COMPLETE ----------------

    elif action == "complete":
        if status not in {
            "paid",
            "cod_pending",
            "delivery_fee_paid",
        }:
            return await callback.answer(
                "This order is not ready to be completed.",
                show_alert=True,
            )

        await update_order_status(order_id, "delivered")

        # Deduct stock exactly once, when the order is completed.
        for order_item in items:
            await decrement_stock(
                order_item["product_id"],
                order_item.get("qty", 1),
            )

        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=t["order_completed"],
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text=t["btn_main_menu"],
                            callback_data="menu_main",
                        )
                    ]]
                ),
            )
        except Exception as e:
            print(f"Could not notify customer about completion: {e}")

        await edit_admin_message(
            callback.message,
            "✅ **ORDER COMPLETED SUCCESSFULLY**",
            None,
        )

        return await callback.answer("Order completed.")

    # ---------------- CANCEL ORDER ----------------

    elif action == "cancel":
        if status in TERMINAL_ORDER_STATUSES:
            return await callback.answer(
                "This order has already been processed.",
                show_alert=True,
            )

        cancellation_status = (
            "cancelled_after_fee"
            if status in DELIVERY_FEE_PAID_STATUSES
            else "cancelled"
        )

        await update_order_status(
            order_id,
            cancellation_status,
        )

        try:
            await callback.bot.send_message(
                chat_id=user_id,
                text=(
                    f"❌ **Your order `{order_id}` has been cancelled "
                    f"by the shop owner.**\n\n"
                    f"Please contact {OWNER_PHONE} if you have questions."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            print(f"Could not notify customer about cancellation: {e}")

        await edit_admin_message(
            callback.message,
            "❌ **ORDER CANCELLED SUCCESSFULLY**",
            None,
        )

        return await callback.answer("Order cancelled.")

    await callback.answer("Unknown action.", show_alert=True)


# ==================================================
# DELIVERY DAYS: 1 DAY / 2 DAYS / 3 DAYS
# ==================================================

@router.callback_query(F.data.startswith("deliver_"))
async def set_delivery_time(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    # Callback format: deliver_<days>_<order_id>
    payload = callback.data.removeprefix("deliver_")

    try:
        days, order_id = payload.split("_", 1)
    except ValueError:
        return await callback.answer("Invalid delivery callback.", show_alert=True)

    if days not in {"1", "2", "3"}:
        return await callback.answer("Invalid delivery time.", show_alert=True)

    order = await get_order(order_id)

    if not order:
        return await callback.answer("Order not found.", show_alert=True)

    if order.get("status") not in {"paid", "cod_pending"}:
        return await callback.answer(
            "This order is not ready for delivery scheduling.",
            show_alert=True,
        )

    user_id = order["user_id"]
    lang = order.get("language", "en")
    t = TEXTS.get(lang, TEXTS["en"])
    item = get_order_item(order)

    delivery_text = t[f"delivery_time_{days}"]

    # Save the selected delivery estimate.
    await update_order_fields(
        order_id,
        {
            "delivery_days": int(days),
            "delivery_time_text": delivery_text,
        },
    )

    user_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=t["btn_main_menu"],
                callback_data="menu_main",
            )
        ]
    ])

    try:
        await callback.bot.send_message(
            chat_id=user_id,
            text=t["delivery_notified"].format(
                days=delivery_text,
                phone=OWNER_PHONE,
            ),
            parse_mode="Markdown",
            reply_markup=user_keyboard,
        )
    except Exception as e:
        print(f"Could not notify customer about delivery time: {e}")

    _, remaining, _ = order_payment_summary(order)

    owner_text = t["owner_order_updated"].format(
        order_id=order_id,
        name=order.get("customer_name", "N/A"),
        phone=order.get("phone_number", "N/A"),
        address=order.get("address", "N/A"),
        item=item.get("name", "Item"),
        size=item.get("size", "N/A"),
        remaining=remaining,
        payment=order.get("payment_method", "COD"),
        days=delivery_text,
    )

    await edit_admin_message(
        callback.message,
        owner_text,
        complete_order_kb(order_id),
    )

    await callback.answer(f"Delivery set to {days} day(s).")


# ==================================================
# ALL ORDERS
# ==================================================

@router.callback_query(F.data == "admin_all_orders")
async def admin_all_orders(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    orders = await get_all_orders()

    if not orders:
        await edit_admin_message(
            callback.message,
            "📭 No orders found.",
            None,
        )
        return await callback.answer()

    text = (
        "📋 **All Orders:**\n\n"
        "Each order button shows its current amount due. "
        "Select an order to view full details."
    )

    await edit_admin_message(
        callback.message,
        text,
        admin_orders_kb(orders),
    )

    await callback.answer()


# ==================================================
# INDIVIDUAL ORDER DETAILS
# ==================================================

@router.callback_query(F.data.startswith("admin_view_order_"))
async def admin_view_order(callback: CallbackQuery):
    if not is_owner(callback):
        return await callback.answer("⛔ Unauthorized.", show_alert=True)

    order_id = callback.data.removeprefix("admin_view_order_")
    order = await get_order(order_id)

    if not order:
        return await callback.answer("Order not found.", show_alert=True)

    item = get_order_item(order)

    status = order.get("status", "unknown")
    display_status = status.replace("_", " ").title()

    if status == "cod_pending":
        display_status = "Cash on Delivery"
    elif status == "pending_payment":
        display_status = "Payment Awaiting Approval"
    elif status == "paid":
        display_status = "Paid"

    total, remaining, fee_paid = order_payment_summary(order)

    delivery_status = (
        "Paid / Verified"
        if fee_paid
        else "Not yet verified"
    )

    payment_method = (
        order.get("payment_method") or "Not selected"
    ).replace("_", " ").title()

    delivery_time = order.get("delivery_time_text", "Not scheduled")

    text = (
        f"📦 **Order Details**\n\n"
        f"🆔 Order: `{order_id}`\n"
        f"👤 Name: {order.get('customer_name', 'N/A')}\n"
        f"📞 Phone: {order.get('phone_number', 'N/A')}\n"
        f"📍 Address: {order.get('address', 'N/A')}\n\n"
        f"👗 Item: {item.get('name', 'N/A')} "
        f"(Size: {item.get('size', 'N/A')})\n"
        f"💰 Order Total: {total:g} ETB\n"
        f"🚚 Delivery Fee: {DELIVERY_FEE} ETB ({delivery_status})\n"
        f"💵 **Remaining to Collect: {remaining:g} ETB**\n"
        f"💳 Payment: {payment_method}\n"
        f"📅 Delivery Time: {delivery_time}\n"
        f"📊 Status: {display_status}"
    )

    await edit_admin_message(
        callback.message,
        text,
        admin_back_orders_kb(order_id, status),
    )

    await callback.answer()
