from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID
from database import get_order, update_order_status, decrement_stock, increment_stock
from locales import TEXTS

router = Router()
DELIVERY_FEE = 300
OWNER_PHONE = "+251927982723"

@router.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("⛔ You are not the owner.", show_alert=True)
        return

    _, action, order_id = callback.data.split("_", 2)
    order = await get_order(order_id)

    if not order:
        await callback.answer("Order not found in DB.", show_alert=True)
        return

    user_id = order["user_id"]
    
    # Fetch language from the database
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    
    item = order['items'][0]

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
        # Stock is only decremented upon delivery for COD
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(chat_id=user_id, text=f"🚚 **Order Delivered!**\nOrder `{order_id}` has been delivered. Thank you!", parse_mode="Markdown")
        await callback.message.edit_text(text=(callback.message.text or "") + "\n\n✅ **DELIVERED**", parse_mode="Markdown")

    # --- REJECT / CANCEL ---
    elif action == "reject":
        await update_order_status(order_id, "rejected")
        
        # If it was already marked as paid/delivered, we should restore stock
        if order['status'] in ["paid", "delivered"]:
            for item in order.get("items", []):
                await increment_stock(item["product_id"], item.get("qty", 1))

        # FIXED: Check if the user had already paid the delivery fee
        if order.get('status') == "delivery_fee_paid":
            # The user has already paid the delivery fee. Use the specific message.
            reject_msg = t["owner_pay_now_rejected"].format(
                item=item['name'],
                phone=OWNER_PHONE
            )
        else:
            # Fallback for other rejection scenarios
            reject_msg = t["order_rejected"].format(phone=OWNER_PHONE)

        # Build the keyboard manually here
        user_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_main_menu"], callback_data="menu_main")]
        ])
        
        await callback.bot.send_message(
            chat_id=user_id, 
            text=reject_msg, 
            reply_markup=user_kb,
            parse_mode="Markdown"
        )
        
        if callback.message.caption:
            await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ **REJECTED**", parse_mode="Markdown")
        else:
            await callback.message.edit_text(text=(callback.message.text or "") + "\n\n❌ **REJECTED**", parse_mode="Markdown")

    await callback.answer("Action processed successfully.")
