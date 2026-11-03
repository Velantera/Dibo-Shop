from aiogram import Router, F
from aiogram.types import CallbackQuery
from config import OWNER_ID
from database import get_order, update_order_status, decrement_stock

router = Router()

@router.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery):
    # Security check: Ensure only the OWNER can click these buttons
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ You are not the owner.", show_alert=True)
        return

    _, action, order_id = callback.data.split("_", 2)
    order = await get_order(order_id)

    if not order:
        await callback.answer("Order not found in DB.", show_alert=True)
        return

    user_id = order["user_id"]

    # --- APPROVE PAY NOW ---
    if action == "approve":
        await update_order_status(order_id, "paid")
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(chat_id=user_id, text=f"🎉 **Payment Confirmed!**\nOrder `{order_id}` is now being processed.", parse_mode="Markdown")
        await callback.message.edit_caption(caption=(callback.message.caption or "") + "\n\n✅ **APPROVED**", parse_mode="Markdown")

    # --- DELIVER COD ---
    elif action == "delivered":
        await update_order_status(order_id, "delivered")
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(chat_id=user_id, text=f"🚚 **Order Delivered!**\nOrder `{order_id}` has been delivered. Thank you!", parse_mode="Markdown")
        await callback.message.edit_text(text=(callback.message.text or "") + "\n\n✅ **DELIVERED**", parse_mode="Markdown")

    # --- REJECT ---
    elif action == "reject":
        await update_order_status(order_id, "rejected")
        await callback.bot.send_message(chat_id=user_id, text=f"❌ Order `{order_id}` has been cancelled or payment rejected.", parse_mode="Markdown")
        
        if callback.message.caption:
            await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ **REJECTED**", parse_mode="Markdown")
        else:
            await callback.message.edit_text(text=callback.message.text + "\n\n❌ **REJECTED**", parse_mode="Markdown")

    await callback.answer("Action processed successfully.")
