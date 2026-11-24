# أرشيف شموع الدقيقة

مصدر مجاني فقط. لا تنبيهات ولا أوامر.

## Yahoo

المجلدات: `SPY` و`GSPC` (^GSPC) و`QQQ` و`VIX` و`VIX1D`. كل ملف `YYYY-MM-DD.csv.gz` هو جلسة نيويورك كاملة بما توفر من ما قبل السوق وما بعده. الملف الموجود لا يُستبدل.

GitHub يشغّل الأرشفة عند 01:15 UTC من الثلاثاء إلى السبت، بعد إغلاق التمديد الساعة 20:00 نيويورك. التشغيل اليدوي:

```bash
python archive_1m.py --source yahoo --out data/archive
```

## IBKR backfill on your PC / تعبئة IBKR على جهازك

No paid real-time subscription. TWS or IB Gateway must already be open, with the API enabled and 127.0.0.1 trusted. Delayed and historical bars are requested with `reqMarketDataType(3)` and then `4`. Symbols without permission are reported as `NO_PERMISSION` and the others continue. This command was not run against a live IBKR session here; unit tests mock the client.

بلا اشتراك لحظي مدفوع. افتح TWS أو IB Gateway أولًا، وفعّل API، واسمح لـ 127.0.0.1. الأمر الواحد يجلب نحو ستة أشهر من شموع الدقيقة (جلسة عادية فقط) لـ SPY وQQQ وSPX وVIX وVIX1D، ويتخطى الأيام المحفوظة، ويلتزم بحدود سرعة IBKR:

```bat
python -m pip install -r requirements.txt -r requirements-ibkr.txt
python archive_1m.py --source ibkr --backfill-days 180 --use-rth 1 --port 7496
```

Gateway on port 4001 instead of TWS:

```bat
python archive_1m.py --source ibkr --backfill-days 180 --use-rth 1 --port 4001
```

ملفات IBKR: `data/archive/ibkr/<SPY|QQQ|SPX|VIX|VIX1D>/<YYYY-MM-DD>.csv.gz`. اليوم الموجود لا يُطلب مرة أخرى. أعد الأمر نفسه إذا انقطع؛ يكمل من حيث توقف. ثم أرسل الأرشيف:

```bat
git add data/archive
git commit -m "Add IBKR 1-minute backfill"
git push
```

Then rerun the study on the full history (train / validation / last fifth as the test):

```bat
python research_1m_lead.py --archive data/archive/ibkr --output artifacts/explosion_1m/ibkr_backfill_report.json
```

العينة الطويلة الجاهزة (Dukascopy، 2025-01-02 حتى 2026-11-10) في `data/archive/dukascopy/spx_history`. نتيجتها في `artifacts/explosion_long/REPORT.md`: **NOT READY**. إعادة الحساب:

```bash
python long_explosion_study.py --root data/archive/dukascopy/spx_history --output artifacts/explosion_long/report.json
```

Yahoo days through 2026-11-10 stay consumed. A later Yahoo-only rerun still uses:

```bash
python research_1m_lead.py --archive data/archive --spent-through 2026-11-10 --output artifacts/explosion_1m/future_report.json
```
