from aiogram import Router, F
from aiogram.types import CallbackQuery
from config import OWNER_ID
from database import get_order, update_order_status, decrement_stock, increment_stock
from keyboards import confirm_approve_kb, confirm_reject_kb, confirm_complete_kb
from locales import TEXTS

router = Router()
DELIVERY_FEE = 300
OWNER_PHONE = "+251927982723"

@router.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ You are not the owner.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 3:
        return await callback.answer()

    _, action, order_id = callback.data.split("_", 2)

    # --- INTERCEPT ACTIONS TO SHOW CONFIRMATION ---
    if action == "approve":
        if callback.message.caption:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n⚠️ **Are you sure you want to APPROVE this payment?**",
                reply_markup=confirm_approve_kb(order_id),
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                text=(callback.message.text or "") + "\n\n⚠️ **Are you sure you want to APPROVE this payment?**",
                reply_markup=confirm_approve_kb(order_id),
                parse_mode="Markdown"
            )
        await callback.answer()
        return

    if action == "reject":
        if callback.message.caption:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n⚠️ **Are you sure you want to REJECT this order?**",
                reply_markup=confirm_reject_kb(order_id),
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                text=(callback.message.text or "") + "\n\n⚠️ **Are you sure you want to REJECT this order?**",
                reply_markup=confirm_reject_kb(order_id),
                parse_mode="Markdown"
            )
        await callback.answer()
        return
        
    if action == "complete":
        if callback.message.caption:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n⚠️ **Are you sure you want to mark this order as COMPLETED?**",
                reply_markup=confirm_complete_kb(order_id),
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text(
                text=(callback.message.text or "") + "\n\n⚠️ **Are you sure you want to mark this order as COMPLETED?**",
                reply_markup=confirm_complete_kb(order_id),
                parse_mode="Markdown"
            )
        await callback.answer()
        return

    # --- PROCESS CONFIRMED ACTIONS ---
    order = await get_order(order_id)
    if not order:
        await callback.answer("Order not found in DB.", show_alert=True)
        return

    user_id = order["user_id"]
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    item = order['items'][0]

    if action == "confirm_approve":
        if order.get('status') == 'paid':
            return await callback.answer("✅ This order is already approved.", show_alert=True)
            
        await update_order_status(order_id, "paid")
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(chat_id=user_id, text=f"🎉 **Payment Confirmed!**\nOrder `{order_id}` is now being processed.", parse_mode="Markdown")
        
        await callback.message.edit_caption(
            caption="✅ **Payment Approved & Order Processed Successfully!**", 
            parse_mode="Markdown",
            reply_markup=None
        )
        await callback.answer("Approved successfully!")

    elif action == "confirm_reject":
        if order.get('status') == 'rejected':
            return await callback.answer("❌ This order is already rejected.", show_alert=True)

        await update_order_status(order_id, "rejected")
        
        if order['status'] in ["paid", "delivered"]:
            for item in order.get("items", []):
                await increment_stock(item["product_id"], item.get("qty", 1))

        if order.get('payment_method') in ['telebirr', 'cbe'] and order.get('status') == "pending_payment":
            reject_msg = t["owner_pay_now_rejected"].format(item=item['name'], phone=OWNER_PHONE)
        else:
            reject_msg = t["order_rejected"].format(phone=OWNER_PHONE)

        await callback.bot.send_message(chat_id=user_id, text=reject_msg, parse_mode="Markdown")
        
        await callback.message.edit_caption(
            caption="❌ **Order Rejected Successfully!**", 
            parse_mode="Markdown",
            reply_markup=None
        )
        await callback.answer("Order rejected!")

    elif action == "confirm_complete":
        if order.get('status') == 'delivered':
            return await callback.answer("✅ This order is already marked as delivered.", show_alert=True)

        await update_order_status(order_id, "delivered")
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(chat_id=user_id, text=f"🚚 **Order Delivered!**\nOrder `{order_id}` has been delivered. Thank you!", parse_mode="Markdown")
        
        await callback.message.edit_caption(
            caption="✅ **Order Completed Successfully!**", 
            parse_mode="Markdown",
            reply_markup=None
        )
        await callback.answer("Order completed!")
