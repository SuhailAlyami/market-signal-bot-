# نقطة استئناف — سهيل هنتر، SPX النقدي

تعليمات مستمرة لهذه الجلسة وما بعدها: احفظ كل مرحلة مكتملة على GitHub فورًا،
وادفعها إلى فرع العمل، وحدّث طلب السحب. لا تترك العمل على القرص المحلي فقط.
لا تدمج عملًا غير مؤهل في `main` لمجرد حفظه. لا تقرأ الأسرار ولا تغيّر صلاحيات
الحسابات ولا تنفّذ أوامرًا ولا تختلق أسعار خيارات. عند اقتراب حد الجلسة أوقف
أي تجربة جديدة واكتب هنا نقطة الاستئناف حتى لو كانت النتيجة غير مكتملة.

الحالة الآن: **NOT_READY**. لا تنبيهات تجريبية.

## آخر commit

- الفرع: `research/spx-inside-range-20261023`
- آخر commit قبل ملف الاستئناف هذا: `c563f1b7321dc9fcb04246d95ea48faa4c1b94a4`
- رسالة: `Record consumed-session inside-range results without enabling alerts.`
- تثبيت القواعد قبل القياس: `c2e2230c12fd55be46d33361997d60a4f9b801f9`
- أساس الفرع: `212474f69d337b71914b2fe7c8d03c3527341605` على
  `research/spx-only-price-watch-20261022`
- `main` بقي عند `0564c0667be0373a65831c2d514bf51a378ed9bf` ولم يُدمج فيه هذا العمل
- طلب السحب المفتوح السابق: https://github.com/SuhailAlyami/market-signal-bot-/pull/41
  (مسودة، فرعه لم يكن يحتوي فرضية داخل النطاق قبل دفع هذا الاستئناف)

بعد دفع هذا الملف، اعتبر SHA الذي يعيده `git rev-parse HEAD` على الفرع البعيد
هو رأس الاستئناف، لا الرقم أعلاه.

## الملفات التي أُضيفت

لم يُعدَّل كاشف الإنتاج `spx_price_watch.py` ولا `spx_price_runtime.py` ولا
`spx_primary.py`.

- `spx_inside_range.py` — استعداد / تأكيد / إلغاء / خروج
- `research_spx_inside_range.py` — تقييم الشرائح المستهلكة، ورمز الخروج 2
- `tests/test_spx_inside_range.py`
- `docs/SPX_INSIDE_RANGE_PROTOCOL.md` — القواعد قبل التشغيل
- `docs/SPX_INSIDE_RANGE_RESULT.md` — النتيجة السلبية
- `artifacts/spx_inside_range_20261023/result.json` — كل الإشارات والمطابقات
- `RESUME.md` — هذا الملف

## الفرضية والقواعد المجمدة

الإصدار `spx-inside-range-v1`. الإدخال OHLC لمؤشر SPX النقدي فقط. ساعة القرار
هي بداية شمعة المزود زائد دقيقة واحدة. وقت الاستلام لا يُستبدل به، ويُستخدم
فقط داخل `min(received_at, chart_end)` لاستبعاد الشمعة غير المكتملة.

1. استعداد: الشمعة ما زالت داخل أعلى/أدنى الدقائق الثلاث السابقة، وليست مرشح
   `spx-price-watch-v1` ولا مسحًا من جهتين، ومداها لا يتجاوز ATR العشرين
   السابقة، والجسم واتجاه ثلاث دقائق والإغلاق مقابل الإغلاق السابق متفقة.
   موقع الإغلاق >= 0.60 للصعود و<= 0.40 للهبوط. هذه قصّة منشورة سلفًا، ليست
   بحثًا جديدًا.
2. تأكيد: خلال 3 دقائق، مرشح أصلي في الاتجاه نفسه.
3. إلغاء: كسر إغلاق لفتيل الاستعداد، أو انتهاء النافذة، أو استعداد معاكس.
4. خروج: بعد التأكيد، كسر معاكس أو كسر الإبطال أو 10 دقائق.

مقارنة عادلة بتهدئة 10 دقائق من ساعة القرار: داخل النطاق، المرشح الأصلي،
اتجاه جسم آخر شمعة، وعدم إصدار إشارة. لا اختيار فائز بعد الرؤية، ولا إدخال
هذه القاعدة إلى شبكة التدريب القديمة في `docs/SPX_PREMOVE_PROTOCOL.md`.

سبب التأخر الذي بُنيت عليه الفرضية، من العينة المستهلكة لا من قاعدة جديدة:
11/16 أول مرشح سعري عند الامتداد أو بعده؛ 9/16 بلا خانة سبق صارمة لأن قرار
المرساة يساوي بداية الفتيل؛ حركة واحدة أطفأتها الحالة. وصول البيانات الحي غير
مقاس.

## الاختبارات

```powershell
python -m unittest tests.test_spx_inside_range tests.test_spx_extension tests.test_spx_price_watch tests.test_spx_premove -q
```

آخر تشغيل محلي: 25 اختبارًا، نجحت. تغطي السببية وتغيير المستقبل، وفصل
الاستعداد/التأكيد/الإلغاء/الخروج، ورفض الكسر المحلي كاستعداد، وبقاء تسع فجوات
صفرية في تشخيص 22 أكتوبر المنشور. نجاحها ليس دليل سوق.

## النتائج السلبية والإيجابية

المصدر: `artifacts/spx_inside_range_20261023/result.json`.
العقد 416904، CBOE، بصمة المدخل تبدأ بـ `179678e39170`. لا شريحة اجتازت
البوابات (دقة 50%، ويلسون الأدنى 40%، استدعاء مبكر 20%، وسيط سبق دقيقة،
كاذب <= 2 لكل جلسة كاملة).

| الشريحة | الحركات | داخل النطاق مبكرًا | الأصلي | جسم آخر شمعة |
|---|---:|---:|---:|---:|
| 22 أكتوبر حتى 17:29UTC | 16 | 0/13 | 0/17 | 0/20 |
| 22 أكتوبر من 17:30UTC | 12 | 2/9 | 0/12 | 1/14 |
| 21 أكتوبر | 22 | 1/21 | 0/31 | 1/35 |
| 20 أكتوبر جزئي 220/390 | 12 | 0/12 | 0/16 | 1/18 |

جمع وصفي غير مستقل: 3 مبكرة لداخل النطاق و3 لجسم الشمعة و0 للأصلي. الرأس الذي
برر الفرضية = 0. في 20 أكتوبر تفوق جسم الشمعة. ذيل 22 أكتوبر: دقتان 4/9،
وسيط 0.5، وغير مطابق 5؛ تأخير محاكى 0/1/2 دقيقة يجعل المبكر 2/1/1. مطابقة
17:31UTC تختفي عند +1 دقيقة. «تحرير التراجع» المنشور سابقًا التقط أيضًا 2 على
الذيل نفسه بإشارات أقل. لا تُعاد هذه التجربة لاختيار عتبة.

## البيانات وإعادة الجلب

محفوظ داخل المستودع ويمكن إعادة توزيعه مع التاريخ: OHLC الخام في
`artifacts/spx_extension_20261023/raw.json` و
`artifacts/spx_only_development/raw.json` و
`artifacts/spx_halfminute_20261023/raw.json`. لا أسرار ولا معرّف حساب ولا
رابط دخول في هذه الملفات.

الجلسات الناقصة لدراسة 12/4/4 لا تُجلب من هذه البيئة: بوابة IBKR المحلية غير
قابلة للوصول، وطلبات `ONE_MONTH/ONE_MIN` وبديل 10000 شمعة رُفضا سابقًا. على
الجهاز الذي فيه Gateway للقراءة فقط والمنفذ 4001، من غير تثبيت ولا تسجيل دخول
جديد ولا اشتراك خيارات:

```powershell
python run_spx_research.py
```

أو على مرحلتين، كما في `docs/SPX_HISTORY_COLLECTION.md` و
`docs/SPX_CHRONOLOGICAL_STUDY.md`:

```powershell
python collect_spx_sessions.py --end 2026-10-21 --sessions 20 --output .hunter-state/spx-history-20 --port 4001
python evaluate_spx_sessions.py --capture .hunter-state/spx-history-20 --output .hunter-state/spx-study-20.json
```

هذا يشغّل الشبكة القديمة المجمدة فقط. لا تُدخل داخل النطاق إلى تلك الشبكة بعد
رؤية النتائج. جلسات 20 و21 و22 أكتوبر 2026 مستهلكة لفرضية داخل النطاق ولا تصلح
احتجازًا لها. أول جلسة أمامية لم تُرَ بعد هي 23 أكتوبر 2026 بعد الإغلاق، بشرط
تثبيت بروتوكول جديد قبل حساب ناتجها.

## العوائق

- لا تغطية لعشرين جلسة كاملة مستقلة.
- هذه البيئة لا تصل إلى Gateway، ولا يُعاد طلب التاريخ الأطول من هنا.
- الفرضية المجمدة لم تتفوق على خط الأساس البسيط في العدد المبكر.
- 9/16 من رأس 22 أكتوبر غير قابلة للسبق الصارم بأي قاعدة دقيقة مكتملة.
- تأخر الوصول الحي غير مقاس. لا سلسلة خيارات موثّقة.
- طلب سحب خاص بفرع داخل النطاق لم يُؤكد في الجلسة السابقة لأن إنشاء الطلب
  احتاج تأكيدًا تفاعليًا. هذا الاستئناف يدفع الفرع ويحدّث الطلب المفتوح إن
  أمكن، دون دمج في `main`.

## الخطوة التالية وأمرها

لا تبدأ تجربة عتبات جديدة على هذه الملفات. أعد طباعة النتيجة المحفوظة فقط:

```powershell
python research_spx_inside_range.py --input artifacts/spx_extension_20261023/raw.json --output .hunter-state/spx-inside-range-new.json --protocol-commit c2e2230c12fd55be46d33361997d60a4f9b801f9
```

رمز الخروج 2 متوقع ويعني NOT_READY. العمل التالي المسموح، على جهاز Gateway
وبعد تثبيت بروتوكول كتابي قبل رؤية الناتج: التقاط جلسات SPX نقدية كاملة
بتواريخ بعد 2026-10-22، ثم تقييم هذه القواعد نفسها مرة واحدة من غير تعديل.
حتى يحدث ذلك تبقى الحالة NOT_READY والتنبيهات مطفأة.



## تحديث الاستئناف: تصحيح دورة الحالات في 23 أكتوبر

الأصل أعلاه محفوظ. آخر عمل الآن: `spx_inside_range_safe.py` وإصدار lifecycle-v2 منفصل، دون تعديل v1 أو قواعد الأسعار. قبل حساب الأثر ثُبت البروتوكول في `48940e18e031b3f803d494665a2861e121d5a6b2`.

ملفات جديدة: `spx_inside_range_safe.py`، `research_spx_lifecycle_repair.py`، `tests/test_spx_inside_range_safe.py`، `docs/SPX_LIFECYCLE_REPAIR_PROTOCOL.md`، `docs/SPX_LIFECYCLE_REPAIR_RESULT.md`، `artifacts/spx_lifecycle_repair_20261023/result.json`.

المقارنة الوصفية للحالات على نفس الشرائح: 91→83 استعدادًا مقيمًا، و69→60 غير مطابق، والمبكر بقي حالتين. ليست مقارنة بجدول التهدئة ولا تحققًا مستقلًا. أربعة اختبارات جديدة و20 فحص سببية passed. لا تغيير main أو التنبيهات. NOT_READY.

أمر إعادة الإنتاج إلى مسار جديد:
`python research_spx_lifecycle_repair.py --input artifacts/spx_extension_20261023/raw.json --output .hunter-state/spx-lifecycle-repair-new.json --protocol-commit 48940e18e031b3f803d494665a2861e121d5a6b2`

الخطوة البحثية التالية: جلسات كاملة جديدة للقواعد المثبتة، مع قياس وصول حي؛ لا تدوير العتبات على البيانات المستهلكة. لا يُختار v2 كفائز من هذه النتيجة. أحدث commit بعيد يحتوي هذا الملف هو نقطة الاستئناف، ولا يصح الاعتماد على SHA القديم في أعلى المستند.


## تحديث: فرضية توافق الاستعداد والميل

أُضيفت فرضية واحدة spx-consensus-v1، اتفاق inside_range_pressure وslope_projection المجمدين على الاتجاه نفسه في الدقيقة المكتملة. ثُبتت قبل القياس في `f21002340df97cc8dab6a9b20291a958fe0d4833`. لا تغيير في أرقام العتبات ولا اختيار بديل بعد النتيجة.

ملفات: `spx_consensus.py` و`research_spx_consensus.py` و`tests/test_spx_consensus.py` و`docs/SPX_CONSENSUS_PROTOCOL.md` و`docs/SPX_CONSENSUS_RESULT.md` و`artifacts/spx_consensus_20261023/result.json`.

النتيجة الوصفية المستهلكة بالمقارنة بجدول داخل النطاق ذي التهدئة (ليست دورة الحالات): 55→31 إشارة، 40→23 غير مطابق، 3→2 مبكر، والمطابقة 15/55→8/31؛ ليست أفضلية مثبتة ولم تُعتمد. NOT_READY والتنبيهات معطلة. لا تعيد تعديلها على نفس البيانات. أربعة اختبارات جديدة للاتفاق والسببية والتحويل الخطي.

إعادة الإنتاج إلى ملف جديد:
`python research_spx_consensus.py --input artifacts/spx_extension_20261023/raw.json --output .hunter-state/spx-consensus-new.json --protocol-commit f21002340df97cc8dab6a9b20291a958fe0d4833`

الخطوة التالية ما زالت بيانات جلسات جديدة كاملة؛ لا يكفي جمع شروط أكثر. أصل التجارب محفوظ، وهذا آخر تحديث وليس نجاحًا تجاريًا. رأس الفرع البعيد الذي يحتوي هذا الملف هو نقطة الاستئناف.


## عامل Codex محلي مجدول

أضيف tools/spx_research_agent.py وtools/install_spx_agent.ps1 ومهمة tools/SPX_AGENT_TASK.md ودليل docs/SPX_LOCAL_AGENT.md. ستة اختبارات موجهة ناجحة محليًا؛ PowerShell/جدولة Windows وCodex الحقيقي وGateway المحلي لم تُختبر أو تُشغّل من هذه البيئة. تثبيت مرة واحدة ينشئ worktree research/local-spx-agent ومهمة عند تسجيل الدخول وكل15دقيقة؛ سقف دورتين ذكيتين/يوم،15دقيقة/دورة. WAIT_DATA ينتظر raw.json جديدًا ولا ينفق رصيدًا على إعادة نفس التجربة. الفشل يحفظ الحالة ويوقف المحاولات، والدفع المتعذر يُعاد قبل عمل جديد. لا نجاح سوقي جديد ولا تفعيل تنبيهات ولا تغيير main. الحالة NOT_READY. الخطوة المحلية: شغّل المثبت كما في الدليل من نسخة فرع البحث ثم تحقق من state.json ورأس الفرع البعيد. لا حاجة إلى نفق Remote Tunnel.


## Local-agent first-cycle checkpoint ? 2026-10-23

The actual scheduled Codex call checked documented127.0.0.1:4001 TCP successfully
at12:17:15UTC. Four existing collector tests passed with SYNTHETIC fixtures only.
It did NOT complete an API handshake or collect new bars; mode/latency remain
UNKNOWN. Its pre-acquisition plan and full honest blocked result are preserved
in docs/SPX_LOCAL_GATEWAY_CHECK_20261023.md and
artifacts/spx_local_gateway_check_20261023/connectivity.json.

The model sandbox blocked linked Git index.lock writes. The host reviewed exactly
these three research checkpoint files and recovered their commit/push without
disabling the sandbox, changing Gateway or resetting the daily call budget.
This recovery is not a market-quality improvement; NOT_READY remains.
Next: execute the already frozen bounded Oct19 daily acquisition ONCE after this
checkpoint is committed, then record actual provider coverage separately.


## تنبيه المستخدم وتوزيع الوكلاء المحليين

أضيف إشعار Windows عند WAIT_DATA/BLOCKED/مراجعة نتيجة، مع needs_gateway=true فقط عند دليل الحاجة إلى فتح البوابة. لا يُستنتج من FROZEN أو إغلاق السوق. منع التكرار مستمر عبر إعادة التشغيل، وattention.txt/json خارج المستودع، وإعادة المحاولة بعد ساعة عند فشل طلب العرض. --test-notification لا يستهلك حصة. 11 اختبارًا موجهًا نجح محليًا (5 جديدة و6 سابقة)؛ Windows الفعلي لم يختبر من هنا. يلزم تحديث العامل المثبت بعد نهاية الدورة الحالية واختبار إشعاره محليًا دون حذف التقدم.

أضيف docs/SPX_MULTI_AGENT_HANDOFF.md: تدقيق بيانات وسببية لـAntigravity، فرضية ومراجعة لوكيلين AionUI، وتنفيذ وقياس لـCodex مع فروع وتسليم SHA. تعليمات جاهزة وليست ادعاء تشغيل التطبيقات المحلية. لا اشتراكات أو مفاتيح جديدة ولا تغيير إنتاج أو تنبيهات سوق؛ NOT_READY. main لم يتغير.


## إصلاح اختبار Windows لترميز العربية

تشغيل GitHub 39953921958 على التحديث 9745929e فشل في اختبار واحد/343 بسبب قراءة attention.json العربي عبر cp1252 الافتراضي. حُدد encoding=utf-8 لجميع قراءات JSON في tests/test_spx_research_agent.py؛ لا تغيير كود العامل أو الكاشف أو Workflow. 11 اختبارًا موجهًا نجح محليًا. يجب تأكيد تشغيل Windows الجديد قبل إعلان زوال فشل CI. لا علاقة مثبتة بالعطل بمصادقة Gateway أو جودة الكشف؛ NOT_READY مستمرة.
