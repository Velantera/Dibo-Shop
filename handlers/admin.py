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
        # 1. Update status
        await update_order_status(order_id, "paid")
        
        # 2. Decrement stock safely
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        # 3. Notify User
        await callback.bot.send_message(
            chat_id=user_id,
            text=f"🎉 **Payment Confirmed!**\n\nOrder `{order_id}` is now being processed. Thank you for shopping with us!",
            parse_mode="Markdown"
        )
        
        # 4. Update Admin Group Message
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n✅ **APPROVED**",
            parse_mode="Markdown"
        )

    elif action == "reject":
        # 1. Update status
        await update_order_status(order_id, "rejected")
        
        # 2. Notify User
        await callback.bot.send_message(
            chat_id=user_id,
            text=f"❌ Payment for order `{order_id}` could not be verified.\n\nPlease contact support if you believe this is an error.",
            parse_mode="Markdown"
        )
        
        # 3. Update Admin Group Message
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + "\n\n❌ **REJECTED**",
            parse_mode="Markdown"
        )

    await callback.answer("Action processed successfully.")
