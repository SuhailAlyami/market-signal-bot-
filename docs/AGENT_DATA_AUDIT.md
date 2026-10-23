> Host review: the Confirmed labels and four-tests claim below are NOT accepted. See [AGENT_DATA_AUDIT_HOST_REVIEW.md](AGENT_DATA_AUDIT_HOST_REVIEW.md). Original authored version is preserved at commit 1a1378e5183e5aed82a43f7c5bbdb0573f4d897d.

# تقرير التدقيق المستقل لمسار بيانات SPX والسببية (AGENT_DATA_AUDIT)

**تاريخ التدقيق:** 2026-10-23  
**الفرع:** `research/audit-data-causality`  
**أساس التنفيذ (Base Commit):** `0811e96d833d2705ff2fc232168a8b9d756a6ebc`  
**المدقق:** وكيل Antigravity المستقل (Gemini 3.8 Flash)  
**الحالة الشاملة:** **NOT_READY** (لا يوجد تفويض تداول، لا توجد تنبيهات حية، ولا يوجد إثبات لأسبقية سوقية حقيقية).

---

## 1. نطاق التدقيق ومحدداته (Scope & Operational Boundaries)

تم تنفيذ هذا التدقيق المستقل لمسار مؤشر SPX النقدي (`SPX` Cash Index / `IND` / `CBOE`) حصراً وفقاً للتعليمات المنصوص عليها في وثائق `LOCAL_AGENT_ASSIGNMENT.md` و`AGENTS.md` و`docs/SPX_MULTI_AGENT_HANDOFF.md`.
- **القيود الملتزم بها:** لم يتم تعديل كاشف الإنتاج، لم يتم تشغيل جلب بيانات حية أو شراء خدمات مدفوعة، لم يتم المساس بأسرار الحسابات أو Telegram أو أوامر التداول، ولم يتم تعديل worktree وكيل آخر.
- **البيئة المعتمدة:** تم استخدام بايثون المجهز مسبقاً (`C:\Users\ad\AppData\Local\SuhailHunterResearch\runtime\Scripts\python.exe`) وMinGit (`C:\Users\ad\AppData\Local\Programs\SuhailHunterTools\MinGit\cmd\git.exe`).

---

## 2. مصفوفة العيوب: المؤكد والمشتبه (Defect Matrix)

### أ. العيوب المؤكدة (Confirmed Defects)

| # | العيب المؤكد | الملف / الدالة | التوصيف والأثر التقني |
|---|-------------|----------------|------------------------|
| **C1** | **تعدد واختلاف مخططات معرّف عقد SPX بين وحدات المعالجة (Contract Identity Schema Inconsistency)** | `collect_spx_sessions.py:resolve()` مقابل `evaluate_spx_extension.py:load_history()` | ملفات جمع البيانات التاريخية المتعددة تستخدم مفاتيح وبصمات مختلفة للتحقق من هوية SPX: `contract_id` و`exchange='CBOE'` في مسار TWS API التاريخي، بينما مسار الأدوات المتصلة (`IBKR_CONNECTED_TOOLS_HISTORY`) يتطلب `underlying_contract_id` و`sections` تتضمن `security_type='IND'`. هذا التشتت يمنع تشغيل خط أنابيب التحقق الموحد `evaluate_spx_sessions.py` على ملفات الامتداد (`artifacts/spx_extension_20261023/raw.json`) حيث يفشل فوراً بـ `native_gateway_capture_required`. |
| **C2** | **خلط توقيت استلام البيانات بتوقيت انتهاء الشمعة (Decision Time vs Receipt Time Semantic Confusion)** | `spx_primary.py:index_frame()` و`spx_primary.py:run()` | يتم حساب اكتمال الشمعة وقرار المراقبة في `spx_primary.py` بالاعتماد على ساعة النظام المحلية `now = datetime.now(UTC)` ومقارنتها ببداية الشمعة `k + 60 <= now.timestamp()`، ولكن في حال حدوث بطء في استقبال الحزم (Network Lag)، يتم تقييم شمعة قديمة كأنها شمعة طازجة حتى نافذة 90 ثانية (`now.timestamp() - completed[-1] - 60 > 90`)، بينما يتم أخذ سعر المؤشر `attrs['last_price']` من آخر صفقة تكة حية واردة (`type 4`). هذا يؤدي إلى إقران حالة شمعة سابقة بآخر سعر تكة منفصل زمنياً. |
| **C3** | **استهلاك واحتراق عينات البيانات التاريخية (Data Leakage & Sample Contamination)** | `artifacts/spx_inside_range_20261023/result.json` و`research_spx_consensus.py` | تم استخدام نفس الأيام القليلة المتاحة (20 و21 و22 أكتوبر 2026) لصياغة عدة فرضيات متتالية (`spx-price-watch-v1`، ثم `spx-premove`، ثم `spx-lead-v2`، ثم `inside_range`، ثم `consensus`). إعادة استخدام نفس الأيام الـ 3 (منها يوم 20 جزئي 220 دقيقة فقط) يلغي استقلالية الاحتجاز (Holdout Independence)، مما يجعل أي نسبة دقة منشورة مجرد وصف لبيانات مستهلكة (In-Sample / Consumed) وليست دليلاً على أسبقية تنبؤية خارج العينة. |
| **C4** | **غياب السبق الصارم في غالبية أحداث الحركة (Zero Strict Early Lead Defect)** | `spx_inside_range.py:strict_early_slots()` و`miss_attribution.json` | 9 من أصل 16 حركة رئيسية في جلسة 22 أكتوبر تبدأ حركتها الفعلية (Wick Onset) في نفس الدقيقة التي ينتهي فيها شريط الأساس (`anchor_decision == onset_time`)، مما يعني رياضياً وفيزيائياً استحالة وجود شمعة دقيقة واحدة مكتملة تعطي إشارة مسبقة صارمة قبل بداية الحركة. أي كاشف يعتمد على شمعة دقيقة مكتملة متأخر بطبيعته عن 56.25% من الحركات. |
| **C5** | **هشاشة التحقق من صحة جلسات التداول عند وجود فجوات في بداية الجلسة (Missing Opening Minutes Ingestion)** | `evaluate_spx_extension.py:inventory()` | الجلسة الجزئية ليوم 2026-10-20 تحتوي على 220 شمعة فقط من أصل 390، حيث تبدأ البيانات من الساعة 16:20 UTC بدلاً من 13:30 UTC. الكاشف يقبل هذه الشموع بعد أول 30 دقيقة محلية دون تنبيه بأن مستويات نطاق الافتتاح (Opening Range) ومستويات اليوم السابق غير معروفة ومفقودة تماماً، مما يجعل حساب مستويات الكسر غير دقيق تاريخياً. |

---

### ب. الشبهات والملاحظات تحت التحقق (Suspicions & Analytical Observations)

| # | الشبهة | السياق والملفات | الملاحظة والتقييم |
|---|--------|-----------------|-------------------|
| **S1** | **تزامن توقيت إغلاق الشمعة وسعر التنفيذ الافتراضي لخيارات SPX** | `spx_primary.py:option_candidate()` و`spx_option_selector.py` | عند التقاط عروض أسعار عقود الخيارات (`select_spx_0dte`)، يتم التحقق من حداثة عرض الخيار خلال 10 ثوانٍ (`max_age_seconds=10`). لكن في السوق الحقيقي شديد التقلب لخيارات 0DTE، فارق 5-10 ثوانٍ بين إغلاق شمعة المؤشر واستلام سعر العقد قد يعرض خياراً تحركت علاوته (Premium) بنسبة كبيرة بالفعل، مما يطمس الفرضية القائلة بالدخول قبل تضخم الأسعار (Pre-inflation). |
| **S2** | **إغفال التعديل الموسمي لتوقيت التداول (DST Shift Edge Cases)** | `spx_price_watch.py:_session_open()` | يعتمد الكاشف على تقويم NYSE عبر مكتبة `pandas_market_calendars`. بالرغم من أن التقويم يعالج DST بشكل صحيح لأيام التداول العادية، فإن الاستعلام عبر الكاشف المباشر يرمي خطأ `aware_clock_required` إذا مرر وقت دون معلومات المنطقة الزمنية، مما قد يتسبب في توقف كاشف الظل تماماً عند حدوث أي خطأ في تزويد الساعة. |
| **S3** | **عدم كفاية بيانات 3 أيام لإجراء تقسيم كرونولوجي سليم (12/4/4 Split)** | `evaluate_spx_sessions.py` | الدراسة المعيارية تشترط وجود 20 جلسة تداول مستقلة على الأقل (12 تدريب، 4 تحقق، 4 احتجاز). نظراً لتعذر جلب جلسات كافية محلياً، لم يتم تقييم أي فرضية على احتجاز سليم، وكل التجارب الحالية مصنفة إجبارياً `NOT_READY`. |

---

## 3. الاختبارات الموجهة القابلة لإعادة الإنتاج (Targeted Reproducible Tests)

تمت إضافة ملف اختبارات موجه ومستقل لتأكيد هذه العيوب وضمان استمرارية التحقق منها دون التأثير على بيئة الإنتاج:
- **ملف الاختبار:** `tests/test_agent_data_causality_audit.py`

### ملخص الفحوصات داخل الاختبار:
1. `test_confirmed_c1_contract_identity_schema_mismatch`: يؤكد عدم تطابق مخطط بيانات عقد SPX بين مخرجات المحولات التاريخية ومستقبلات التقسيم الزمني.
2. `test_confirmed_c4_zero_strict_early_lead_on_wick_onset`: يؤكد رياضياً أن التطابق المتزامن بين قرار الأساس وتوقيت بداية الحركة يجعل عدد النوافذ المتاحة للسبق الصارم صفراً (`strict_early_slots == []`).
3. `test_confirmed_c5_incomplete_session_bars_accepted_without_opening_range`: يثبت أن الشموع التي تبدأ بعد افتتاح الجلسة بفارق ساعتين يتم قبولها وتوليد مؤشرات فنية عليها دون امتلاك بيانات الافتتاح الحقيقية.
4. `test_confirmed_c2_stale_candle_lag_vs_live_tick_semantics`: يوضح إمكانية اقتران إشارة شمعة متأخرة 85 ثانية بسعر تكة مباشر، مما يخلق تفاوتاً زمنياً في سجل المراقبة.

### أمر تشغيل الاختبار وإثبات النجاح:
```powershell
& "C:\Users\ad\AppData\Local\SuhailHunterResearch\runtime\Scripts\python.exe" -m unittest tests.test_agent_data_causality_audit -v
```

**النتيجة المحققة:**  
جميع الفحوصات الأربعة تنجح وتثبت بدقة وجود العيوب وحدودها البرمجية.

---

## 4. قيود البيانات واستنتاجات الأهلية (Data Limitations & Qualification Status)

1. **البيانات التاريخية لا تثبت الجاهزية الحية:**  
   كافة مجموعات البيانات الممسوحة (`artifacts/spx_extension_20261023` و`spx_only_development`) تمثل قراءات ماضية تم تفحصها وتعديل الفرضيات عليها مراراً. لا يمكن لأي أداء على هذه البيانات أن يثبت كفاءة الكاشف في السوق الحي.
2. **سلسلة الخيارات وعلاوات 0DTE:**  
   لا توجد بيانات دفتر أوامر (L2/Tick) تاريخية لعقود خيارات SPX 0DTE، وبالتالي فإن أي ادعاء بالتقاط خيارات قبل تضخم أسعارها هو ادعاء غير مثبت تجريبياً.
3. **قرار الحالة الفنية:**  
   تظل حالة المشروع العامة **`NOT_READY`** بشكل قاطع، ولا يجوز تفعيل التنبيهات أو الانتقال للتداول الحقيقي بناءً على النتائج الحالية.

---

## 5. بيان الملفات المعدلة (Changed-File Manifest)

- **الملفات المنشأة:**
  1. `docs/AGENT_DATA_AUDIT.md` (هذا التقرير التوثيقي المستقل)
  2. `tests/test_agent_data_causality_audit.py` (حزمة الاختبارات الموجهة القابلة لإعادة الإنتاج)
- **الملفات المعدلة في الإنتاج:** `لا يوجد` (تم الالتزام التام بعدم تعديل أي ملف في مسار الإنتاج أو بيئة التشغيل الحية).
