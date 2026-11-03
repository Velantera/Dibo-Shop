from aiogram import Router, F
from aiogram.types import CallbackQuery
from database import update_order_status, get_order

router = Router()

@router.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery):
    # Security: only respond in admin group (can also add user ID whitelist)
    _, action, order_id_str = callback.data.split("_")
    order_id = int(order_id_str)

    order = await get_order(order_id)
    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    user_id = order[1]

    if action == "approve":
        await update_order_status(order_id, "paid")
        await callback.bot.send_message(
            chat_id=user_id,
            text=f"🎉 **Payment Confirmed!**\nOrder #{order_id} is now being processed. Thank you!"
        )
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ **APPROVED**",
            parse_mode="Markdown"
        )
    elif action == "reject":
        await update_order_status(order_id, "rejected")
        await callback.bot.send_message(
            chat_id=user_id,
            text=f"❌ Payment for Order #{order_id} could not be verified. Please contact support."
        )
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ **REJECTED**",
            parse_mode="Markdown"
        )

    await callback.answer()
