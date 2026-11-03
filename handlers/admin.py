from aiogram import Router, F
from aiogram.types import CallbackQuery
from database import get_order, update_order_status, decrement_stock

router = Router()

@router.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery):
    _, action, order_id = callback.data.split("_", 2)
    order = await get_order(order_id)

    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    user_id = order["user_id"]

    if action == "approve":
        await update_order_status(order_id, "paid")
        # Decrement stock for each item
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(
            chat_id=user_id,
            text=f"🎉 **Payment Confirmed!**\nOrder `{order_id}` is now being processed. Thank you!",
            parse_mode="Markdown"
        )
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ **APPROVED**",
            parse_mode="Markdown"
        )

    elif action == "reject":
        await update_order_status(order_id, "rejected")
        await callback.bot.send_message(
            chat_id=user_id,
            text=f"❌ Payment for order `{order_id}` could not be verified. Please contact support.",
            parse_mode="Markdown"
        )
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n❌ **REJECTED**",
            parse_mode="Markdown"
        )

    await callback.answer()
