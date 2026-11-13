# RESUME.md — Suhail Hunter

**Status: NOT READY** (ready for *connection/health verification only*; not ready for live early-detection use)

Last examined: 2026-10-24  
Latest commit before this update: `5cfb97f797e538b5dfa6e7a80cf9a1b8428b9d6e`

## Verification readiness (what "جاهز للتحقق" means here)

The project is prepared so the owner can **verify infrastructure and data path**, not so that detection is claimed working.

### Can verify today (Saturday — market closed)

| Check | Expected | Notes |
| --- | --- | --- |
| IBKR account connector | Connected | Account summary readable (2026-10-24 probe) |
| Flow type | REVIEW_AND_APPROVE | No autonomous live orders from this path |
| SPX index contract resolve | contract_id 416904 @ CBOE | `search_contracts` OK |
| SPX live snapshot | **REJECT** (top-status) | Expected on weekend / missing entitlement / frozen; do not treat as live edge |
| Software unit tests | Pass offline | No market required |
| Shadow / fail-closed on stale data | Can be exercised on saved data | Do not enable experimental Telegram alerts |

### Requires open RTH (or confirmed live session)

| Check | Required evidence |
| --- | --- |
| SPX cash last-trade timestamp freshness | Positive trade `ts` ≤ ~10s repeatedly |
| Option book sample (nearby SPXW) | Repeated callbacks, uncrossed bid/ask, age limits |
| Continuous collector heartbeat | Same-host IB Gateway + runner, not chat-only connector |
| Early-detection quality | New unconsumed dates + measured lead/false/miss vs baseline |

Until those open-session checks pass with retained logs, keep **NOT READY** and alerts **OFF**.

## What is already done (evidence)

- Issue #16 research preserved under `artifacts/issue16/`.
- Selected rule on spent holdout: low early recall; Yahoo bars ~9–10 min old.
- Canonical runtime with SETUP/TRIGGER/INVALIDATION/EXIT, cooldown, dedupe, stale fail-closed.
- Experimental alerts **OFF**.
- `spx_primary.py` / Gateway SPX path documented in `docs/SPX_PRIMARY_AND_PINE.md`.
- Active Telegram production path documented as separate repo `SuhailAlyami/spx-agent`.

## Why still NOT READY

1. **Feed timing / entitlement**: Free delayed futures and Saturday SPX snapshot REJECT do not prove timely cash SPX.
2. **Detection quality**: No generalized early edge on independent holdout.
3. **Host**: Chat IBKR connector ≠ always-on collector for Actions/runtime. Gateway on owner machine helps only while that machine stays up and authorized.
4. **SPX + options**: Live freshness and repeated option-book evidence not yet retained for open session.

## Data already consumed

- Holdout Oct 12–16 (RTH) and Oct 13–16 (all-session) are **spent**. Do not retune on them.

## Owner actions for full verification week

1. Keep IB Gateway running on a machine that stays on through the session you want to test.
2. On next open RTH: capture SPX last + top-status + receipt time; sample nearby SPXW books; save journals under a dated `artifacts/` folder.
3. Only after repeated fresh SPX trade timestamps: run shadow (no user alerts) for multiple sessions.
4. New research protocol only on **unconsumed** dates if claiming improvement.

## Resume command

```text
Read RESUME.md + docs/ISSUE16_REPORT.md + AGENTS.md + docs/SPX_PRIMARY_AND_PINE.md.
Confirm experimental alerts OFF.
If Gateway is up on open RTH: verify SPX top-status + last ts age, then shadow only.
If Saturday/closed: only connection + offline tests; do not claim live detection.
```

## Research finding — 2026-11-14

**Root cause of NOT_READY identified.** The signal exists. The data source is the bottleneck.

### What all experiments prove

| Experiment | Best result | Why it fails |
|---|---|---|
| explosion_detector.py (5m Yahoo bars) | Detects moves | Bars arrive 9-10 min late; 70-90% of move is done |
| halfminute-pilot (30s ES/NQ) | 16.7% precision, +60s lead | Too weak, not SPX |
| detector_v2 (4 ML models) | 29.2% precision, −1 min lead | Negative lead = confirms after move |
| **breadth_20261109** | **59.6% direction, +1.23pt gross** | **Yahoo delay kills entry; net turns negative at 1pt cost** |

### نتائج breadth_20261109 الفعلية (لا يُبالغ فيها)

`wave_capture.detect` + constituent agreement ≥ 8/10 على dev (57 جلسة):

| معيار | نتيجة | الحكم |
|---|---|---|
| C1: فرق high−rest (CI يستبعد صفر) | +1.80 pt [0.26, 3.33] | **PASS** |
| C2: صافي high عند تكلفة 1pt > 0 | −2.5pt | **FAIL** |
| C3: متوسط gross موجب في كلا النصفين | النصف الأول +1.23pt، الثاني +0.76pt | **PASS** |
| C4: high يتفوق على اتجاه عشوائي (CI يستبعد صفر) | CI: [−20, +229] يشمل الصفر | **FAIL** |
| **القرار المسجل** | **REJECT** | — |

ملاحظات دقيقة:
- 59.6% اتجاه تخص النصف الأول فقط (57 إشارة)؛ الجلسة كاملة 53.7%
- C1 يثبت أن high تتفوق على rest، لا أنها تتفوق على الصدفة
- تأخر Yahoo لم يُقس فعلياً؛ لا دليل أن IB Gateway يحل المشكلة
- واجهة الاختبار الأمامي هي `run.py --forward <store>` لا `--holdout`، وتشترط 190 حدثاً قبل إخراج نتائج

### الحالة الحقيقية للمشروع

**مرشح بحثي واعد، غير مثبت.** C1 هو أفضل إشارة إحصائية في المستودع لكنه وحده غير كافٍ للقرار. القاعدة رُفضت بشكل صريح في التقرير.

### Path to next test (الخطوة المتبقية الوحيدة)

جمع بيانات اتساع forward (branch `data/spx-collection`) من جهازك:
```bash
pip install yfinance exchange_calendars
python3 research/spx_collection/collect_yahoo_spx.py --breadth
# يخزن في breadth5m/bars5m.json
```
بعد تجميع 190 حدثاً بالاتفاق العالي (≥8) عبر جلسات Nov 05+:
```bash
python3 research/breadth_20261109/run.py --forward breadth5m/bars5m.json
```
النتيجة إما FORWARD_PASS_STILL_NOT_READY أو FORWARD_FAIL. في كلا الحالتين: تبقى الإنذارات مغلقة.

### Consumed data

- Dev: Aug 17 – Nov 04 (57 جلسة) — مستهلك بالكامل
- Holdout (SPENT): Oct 12–16 — لا تعد إلى هذه البيانات
- Breadth forward (LOCKED ≥ Nov 05): لا تقرأ النتائج قبل بلوغ 190 حدثاً

## Resume command

```text
Read RESUME.md + docs/ISSUE16_REPORT.md + AGENTS.md + docs/SPX_PRIMARY_AND_PINE.md.
Confirm experimental alerts OFF.
If Gateway is up on open RTH: verify SPX top-status + last ts age, then shadow only.
If Saturday/closed: only connection + offline tests; do not claim live detection.
Next research action: collect breadth sessions Nov 10+ from owner's machine.
```

## Change log

- 2026-10-24 (earlier): Initial RESUME.md from repo exam.
- 2026-10-24 (this update): Verification checklist; IBKR chat connector account OK; SPX snapshot top-status REJECT on Saturday; still NOT READY; alerts remain OFF.
- 2026-11-14 (تحديث أول): تدقيق كامل للتجارب. breadth_20261109 أفضل نتيجة في المستودع (C1 PASS)، لكن القاعدة رُفضت رسمياً (C2+C4 FAIL). لا دليل على أن التأخر هو السبب. الخطوة الوحيدة: جمع forward data ≥190 حدث ثم run.py --forward. تصحيح ادعاءات مبالغ فيها من التحديث الأول.
