# سهيل هنتر على Cloudflare Workers (مجاني، دائم، Telegram فقط)

- ملف واحد: `src/index.js`. فيه رسالة الصباح، وتحديث الساعة الأولى، ونتيجة المساء، والسجل الحي.
- مؤقت واحد كل 5 دقائق. الكود يختار المهمة حسب وقت نيويورك:
  - 08:40 رسالة الصباح
  - 10:40 تحديث الساعة الأولى
  - كل 5 دقائق أثناء الجلسة: كاشف كسر الصندوق مع الحجم، ويرسل الإشارة مرة واحدة
  - بعد الإغلاق بـ 20 دقيقة نتيجة المساء
- لا يعتمد على GitHub Actions ولا على أي تخزين. كل رسالة تُبنى من بيانات Yahoo العامة.
- عند فشل البيانات يُسجَّل الخطأ داخلياً فقط، ولا تصلك رسالة خطأ.
- الاختبارات: `node --test test/worker.test.js` (14 اختباراً). نتائجها مطابقة لنسخة Python.

## التشغيل (مرة واحدة)
1. dash.cloudflare.com ← Workers & Pages ← Create ← Import a repository ← اختر `market-signal-bot-`. في Root directory اكتب `worker` ثم Deploy.
2. في الـ Worker افتح Settings ← Variables and Secrets، وأضف كسر (Secret):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `RUN_KEY` (أي كلمة سر، اختياري)
3. للتجربة الفورية: `https://<worker>.workers.dev/run?job=morning&key=<RUN_KEY>`

تقويم البورصة مكتوب حتى نهاية 2027 من nyse.com، ويجب تمديده سنوياً.
