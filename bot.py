# bot.py
import os
import logging
from flask import Flask, request, abort
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler

# --- إعداد السجل ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- قراءة متغيرات البيئة ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")  # ضع توكن البوت هنا كمتغير بيئة
OWNER_ID = int(os.environ.get("OWNER_ID", "5581457665"))  # المستخدم الوحيد المسموح به (افتراضي كما طلبت)
CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "@qd3qd")  # اسم القناة (مع @)

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN غير مُحدد في متغيرات البيئة")

bot = Bot(token=TELEGRAM_TOKEN)
app = Flask(__name__)

# --- Dispatcher مستقل للتعامل مع التحديثات (webhook) ---
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

# --- رسائل ثابتة ---
MSG_FORBIDDEN = "ممنوع — هذا البوت غير متاح لك."
MSG_NOT_SUBSCRIBED = "الرجاء الاشتراك في القناة {} لاستخدام البوت.".format(CHANNEL_USERNAME)
MSG_WELCOME = "أهلاً! يمكنك استخدام أزرار التحكم أدناه."

# --- مساعد: التحقق من اشتراك المستخدم في القناة ---
def is_subscribed(user_id: int) -> bool:
    try:
        member = bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        status = member.status  # 'creator','administrator','member','restricted','left','kicked'
        logger.info("user %s subscription status in %s: %s", user_id, CHANNEL_USERNAME, status)
        return status in ("creator", "administrator", "member", "restricted")
    except TelegramError as e:
        # لو القناة خاصة أو خطأ آخر -> اعتبره غير مشترك (يمكن تسجيل الخطأ)
        logger.warning("خطأ في فحص الاشتراك: %s", e)
        return False

# --- أزرار بسيطة ---
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("التحقق من الاشتراك", callback_data="check_sub")],
        [InlineKeyboardButton("معلومات", callback_data="info")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- handlers ---
def start(update, context):
    user = update.effective_user
    user_id = user.id
    logger.info("/start from user %s (%s)", user_id, user.username)

    if user_id != OWNER_ID:
        update.message.reply_text(MSG_FORBIDDEN)
        return

    # الآن نتحقق من الاشتراك
    if not is_subscribed(user_id):
        update.message.reply_text(MSG_NOT_SUBSCRIBED)
        return

    # مسموح — نعرض الأزرار
    update.message.reply_text(MSG_WELCOME, reply_markup=main_keyboard())

def info_handler(update, context):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        update.message.reply_text(MSG_FORBIDDEN)
        return
    update.message.reply_text("هذا بوت تحكم بسيط. فقط المالك المسموح له يستخدم هذه الوظائف.")

def callback_query_handler(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    # لا تنسى الرد على callback لتفادي أي دوائر تحميل في تيليجرام
    query.answer()

    if user_id != OWNER_ID:
        query.edit_message_text(MSG_FORBIDDEN)
        return

    if data == "check_sub":
        if is_subscribed(user_id):
            query.edit_message_text("تم التحقق: أنت مشترك في {} ✅".format(CHANNEL_USERNAME))
        else:
            query.edit_message_text(MSG_NOT_SUBSCRIBED)
    elif data == "info":
        query.edit_message_text("معلومات: هذا بوت لعرض أزرار والتحقق من الاشتراك.")

# --- تسجيل المعالجات في الـ Dispatcher ---
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("info", info_handler))
dispatcher.add_handler(CallbackQueryHandler(callback_query_handler))

# --- Webhook endpoint (Render سيطلب هذا) ---
@app.route("/webhook/{}".format(TELEGRAM_TOKEN), methods=["POST"])
def webhook():
    # تأكد أن الطلب من تيليجرام (يمكن إضافة تحقق إضافي إذا رغبت)
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
        return "OK"
    else:
        abort(403)

# --- وظيفة مساعدة: تسجيل الـ webhook عند الإقلاع (اختياري) ---
def set_webhook():
    """
    إذا قمت بتعيين متغير البيئة RENDER_EXTERNAL_URL إلى رابط الخدمة (مثلاً
    https://your-service.onrender.com) سيتم تسجيل webhook تلقائياً.
    """
    external_url = os.environ.get("RENDER_EXTERNAL_URL")  # ضع رابط الخدمة هنا في إعدادات Render
    if external_url:
        webhook_url = f"{external_url}/webhook/{TELEGRAM_TOKEN}"
        logger.info("Setting webhook to %s", webhook_url)
        try:
            bot.set_webhook(webhook_url)
            logger.info("Webhook set successfully.")
        except TelegramError as e:
            logger.exception("فشل في تعيين webhook: %s", e)
    else:
        logger.info("RENDER_EXTERNAL_URL غير محدد — لم يتم تعيين webhook تلقائياً.")

# --- نقطة البداية عند التشغيل (مثل عبر gunicorn) ---
if __name__ == "__main__":
    set_webhook()
    # لتجربة محلية يمكن تشغيل Flask مباشرة (غير موصى به للـ production on Render)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
