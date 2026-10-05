# البنية | Architecture

نظام السجل المدني وشجرة العائلة — كيف تعمل الطبقات، نموذج البيانات، ومحرّك
القرابة.

Civil Registry & Family Tree — layers, data model and the relationship engine.

---

## 1. نظرة عامة | Overview

```
                     ┌──────────────────────────┐
  HTTP / JSON  ────► │  app/api/v1/*  (routers) │
                     │  auth · validation · audit│
                     └───────────┬──────────────┘
                                 │
                     ┌───────────▼──────────────┐
                     │  app/services/*          │
                     │  business rules,         │
                     │  transactions, auditing  │
                     └───────────┬──────────────┘
                                 │
                     ┌───────────▼──────────────┐
                     │  app/models/* (SQLAlchemy)│
                     └───────────┬──────────────┘
                                 │
                     ┌───────────▼──────────────┐
                     │  PostgreSQL 16           │
                     │  triggers · indexes      │
                     └──────────────────────────┘
```

- **routers** يتحققون من الصلاحيات (`deps.py`)، ويحوّلون `HTTP → service → HTTP`،
  ويسجّلون أحداث التدقيق (قراءة/بحث).
- **services** تحوي كل قواعد العمل: التحقق، التعارضات، الترحيل، الاستيراد،
  الدمج، محرّك القرابة. لا تحتوي على كائنات `Request`/`Response`.
- **models** أعمدة SQLAlchemy 2 (`Mapped[...]`) مع تطبيع مسبق للغة العربية.
- **alembic/0001_initial.py** يملك المخطط والفهارس و`pg_trgm` و*bTree* GIN و
  trigger يمنع الدورات في شجرة الوالدين.

## 2. نموذج البيانات | Data model

```
users ──1:N──► audit_log (SET NULL عند حذف المستخدم)

person (person_id)
  ├─ father_id ──► person        ┐
  ├─ mother_id ──► person        ┼─ self-referencing، مع trigger يمنع الدورات
  ├─ merged_into_id ──► person   ┘  (سجل إحالة بعد الدمج)
  ├─1:N─► marriage (husband_id / wife_id)
  └─N:M─► marriage (عبر persons)

marriage (marriage_id)
  husband_id ──► person (M)
  wife_id    ──► person (F)
  start_date, end_date, status (married | divorced | widowed)

import_job (+ error_report JSONB, column_mapping JSONB, linking_mode)
import_mapping_template
```

- `person.national_id` فريد، و`person.full_name_normalized` فهرس للبحث العربي.
- كل التواريخ `DATE`، وكل الأوقات `TIMESTAMPTZ` بتوقيت التطبيق (`Africa/Cairo`).
- `marriage.status` مشتق: زواج نشط = `married`، منتهٍ = `divorced`، أو `widowed`
  إذا مات الزوج.

## 3. محرّك القرابة | Relationship engine

`app/services/relationship_service.py` — كل الاستدعاءات على مستوى سطر واحد،
بلا recursive queries:

1. **`ancestor_map(person_id, depth)`** يرسم خريطة المسار إلى الجذر
   (`{person_id: generation}`). المسار يُبنى BFS من الشخص للأعلى مع توثيق
   *last hop* لتمييز الأب عن الأم.
2. **الأسلاف/الأبناء** تُقارَن الخريطتان: إذا كان B في خريطة A فهو سلف لـ A
   بـ`generation = map_a[b]`؛ depths تبدأ من 0 عند الشخص نفسه.
3. **الأقارب الجانبيون** = تقاطع الخريطتين → أقرب سلف مشترك (LCA)→
   `_branch_is_paternal` لتحديد paternal أم maternal (عم/خال، ابن العم/ابن
   الخال).
4. **الأصهار** = أزواج individuals على-path القلب.
5. **شجرة العائلة** `tree(person_id, depth)` تُجمّع `up`/`down` + `nodes` +
   `links` (paternal/maternal/ spouse).
6. كل نتيجة تحمل `relation` و`relation_code` و`relation_from_a/b` و
   `generations` و`path` و`explanation` بالعربية. العقد موثّق في
   [DECISIONS.md](DECISIONS.md).

## 4. اللغة العربية | Arabic handling

`app/utils/arabic.py` — تطبيع واحد يُستخدم في البحث والتكرار والمطابقة:

- حذف التشكيل والتطويل (أ إ آ ٱ → ا، ة → ه، ى → ي، ؤ → و).
- **لا** يزيل الألف hopper أو يحوّل ة إلى تاء مربوطة، لأن الأسماء العربية
 Recordedort حينها.
- تحويل الأرقام العربية-الهندية `٠١٢…` → `012…`.
- `parse_full_name` يقسّم الاسم الرباعي (أول/ الأب/ الجد/ العائلة).
- `similarity` = Dice على bigrams — مستخدم لكشف التكرار (انظر DECISIONS).

## 5.Privacy والأمان | Security

- JWT قصير العمر (30 دقيقة) + refresh token (14 يوماً)، Argon2id للكلمات.
- أدوار: `viewer` / `editor` / `admin` (انظر README).
- `viewer` يرى رقم القومى مقنّعاً (`********1234`) عبر `PersonOut.from_model`.
- قفل الحساب بعد `max_login_attempts` محاولات + throttle داخل العملية.
- رؤوس أمان (nosniff، DENY، no-referrer) + CORS بقائمة بيضاء + gzip.
- سجل التدقيق يكتب **كل** قراءة/كتابة/تصدير/استيراد مع `username` و`ip`.

## 6. الاستيراد | Import pipeline

```
upload ──► job(pending) + preview + suggested_mapping
   │            │
   │            └─ POST /mapping (اختياري: يثبّت المطابقة يدوياً)
   ▼
validate ──► تقرير {valid_rows, invalid_rows, errors[{row,field,message}]}
   ▼
commit ──► thread بمقاطع في جلسة مستقلة ──► status(completed|failed)
```

`validate` لا يكتب أي شخص؛ `commit` يكتب على دفعات (chunk) مع تقرير أخطاء لكل
صف فشل. المطابقة المقترحة تُستخدم حتى يؤكدها المستخدم (انظر DECISIONS).

## 7. الاختبارات | Tests

- `tests/conftest.py`: ترحيلات Alembic مرة لكل جلسة + TRUNCATE قبل كل اختبار +
  مستخدمون بأدوار + عينة `sample_family`.
- الملفات: `persons`، `marriages`، `relationships`، `stats`، `exports`،
  `duplicates`، `imports`، `admin`، `auth`، `utils`.
- عيّنة SQL الحقيقية تُقرأ بنفس parser الإنتاج، فهي اختبار للـ seed أيضاً.