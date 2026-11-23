from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_IDS
from database import get_order, update_order_status, decrement_stock, increment_stock
from locales import TEXTS

router = Router()
DELIVERY_FEE = 300
OWNER_PHONE = "+251927982723"

@router.callback_query(F.data.startswith("admin_"))
async def admin_action(callback: CallbackQuery):
    if callback.from_user.id not in OWNER_IDS:
        await callback.answer("⛔ You are not the owner.", show_alert=True)
        return

    parts = callback.data.split("_")
    if len(parts) < 3:
        return await callback.answer()

    _, action, order_id = callback.data.split("_", 2)
    order = await get_order(order_id)

    if not order:
        await callback.answer("Order not found in DB.", show_alert=True)
        return

    user_id = order["user_id"]
    lang = order.get('language', 'en')
    t = TEXTS[lang]
    item = order['items'][0]

    # --- APPROVE PAY NOW ---
    if action == "approve":
        # SAFETY CHECK: Prevent double approval
        if order.get('status') == 'paid':
            return await callback.answer("✅ This order is already approved.", show_alert=True)
            
        await update_order_status(order_id, "paid")
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(chat_id=user_id, text=f"🎉 **Payment Confirmed!**\nOrder `{order_id}` is now being processed.", parse_mode="Markdown")
        
        # Update the caption in the Admin Group
        await callback.message.edit_caption(
            caption=(callback.message.caption or "") + f"\n\n✅ **APPROVED by @{callback.from_user.username or callback.from_user.id}**", 
            parse_mode="Markdown",
            reply_markup=None # Remove the buttons so no one can click them again
        )

    # --- DELIVER COD ---
    elif action == "delivered":
        if order.get('status') == 'delivered':
            return await callback.answer("✅ This order is already marked as delivered.", show_alert=True)

        await update_order_status(order_id, "delivered")
        for item in order.get("items", []):
            await decrement_stock(item["product_id"], item.get("qty", 1))

        await callback.bot.send_message(chat_id=user_id, text=f"🚚 **Order Delivered!**\nOrder `{order_id}` has been delivered. Thank you!", parse_mode="Markdown")
        
        await callback.message.edit_text(
            text=(callback.message.text or "") + f"\n\n✅ **DELIVERED by @{callback.from_user.username or callback.from_user.id}**", 
            parse_mode="Markdown",
            reply_markup=None
        )

    # --- REJECT / CANCEL ---
    elif action == "reject":
        if order.get('status') == 'rejected':
            return await callback.answer("❌ This order is already rejected.", show_alert=True)

        await update_order_status(order_id, "rejected")
        
        if order['status'] in ["paid", "delivered"]:
            for item in order.get("items", []):
                await increment_stock(item["product_id"], item.get("qty", 1))

        if order.get('payment_method') in ['telebirr', 'cbe'] and order.get('status') == "pending_payment":
            reject_msg = t["owner_pay_now_rejected"].format(
                item=item['name'],
                phone=OWNER_PHONE
            )
        else:
            reject_msg = t["order_rejected"].format(phone=OWNER_PHONE)

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
            await callback.message.edit_caption(
                caption=callback.message.caption + f"\n\n❌ **REJECTED by @{callback.from_user.username or callback.from_user.id}**", 
                parse_mode="Markdown",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                text=(callback.message.text or "") + f"\n\n❌ **REJECTED by @{callback.from_user.username or callback.from_user.id}**", 
                parse_mode="Markdown",
                reply_markup=None
            )

    await callback.answer("Action processed successfully.")
