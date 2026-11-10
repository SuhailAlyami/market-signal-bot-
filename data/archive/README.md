# أرشيف شموع الدقيقة

مصدر مجاني فقط. لا تنبيهات ولا أوامر.

## Yahoo

المجلدات: `SPY` و`GSPC` (^GSPC) و`QQQ` و`VIX` و`VIX1D`. كل ملف `YYYY-MM-DD.csv.gz` هو جلسة نيويورك كاملة بما توفر من ما قبل السوق وما بعده. الملف الموجود لا يُستبدل.

GitHub يشغّل الأرشفة عند 01:15 UTC من الثلاثاء إلى السبت، بعد إغلاق التمديد الساعة 20:00 نيويورك. التشغيل اليدوي:

```bash
python archive_1m.py --source yahoo --out data/archive
```

## IBKR على جهازك

افتح TWS أو IB Gateway مع تفعيل API. لا يلزم اشتراك لحظي مدفوع. الأمر الواحد:

```bash
python archive_1m.py --source ibkr
```

المنفذ الافتراضي `4001` (بوابة المستودع). لـ TWS: `python archive_1m.py --source ibkr --port 7496`.  
`--use-rth 1` يحصر الطلب في الجلسة العادية. الرمز بلا صلاحية يُطبع في `NO_PERMISSION` ويكمل الباقي. الملفات تحت `data/archive/ibkr/<SPY|QQQ|SPX|VIX>/`. وقت الاستلام يُسجل مع شموع التاريخ كدفعة، ومع التحديث الحي في `live-YYYY-MM-DD.jsonl` إذا أضفت `--live-seconds 120`.

لم يُشغَّل هذا الأمر على جلسة IBKR حية من بيئة التطوير. الاختبارات تحاكي ردود الوسيط.

## إعادة الدراسة لاحقًا

الجلسات حتى 2026-11-10 مستهلكة. عندما تتوفر 12 جلسة بعدها:

```bash
python research_1m_lead.py --archive data/archive --spent-through 2026-11-10 --output artifacts/explosion_1m/future_report.json
```
