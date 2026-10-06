# واجهة الـ API | API notes

كل المسارات تحت `/api/v1` (يمكن تغييرها بـ `api_prefix`). المرجع الكامل التفاعلي
على `/docs` (Swagger) و`/redoc`. كل الردود JSON إلا ملفات التصدير.

This file documents the contracts that are **not** obvious from the OpenAPI
schema: masking, pagination, auditing and the relationship semantics.

---

## المصادقة | Authentication

```bash
curl -X POST /api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"..."}'
# → {"access_token": "...", "refresh_token": "...", "token_type": "bearer", "user": {...}}
```

- استخدم `Authorization: Bearer <access_token>`.
- `access_token` صالح 30 دقيقة، `refresh_token` 14 يوماً (قابلان للتغيير).
- بعد 5 محاولات فاشلة يُقفل الحساب 15 دقيقة (`POST /users/{id}/unlock` للمدير).
- `GET /config` يعيد إعدادات العميل (الحد الأدنى لسن الوالد، الأدوار التي يقنّع
  رقم القومى، حدود الصفحات) — لا يكشف أي سرّ.

## الترقيم | Pagination

كل القوائم ترجع:

```json
{"items": [...], "total": 42, "page": 1, "page_size": 25, "pages": 2}
```

`page_size` حتى `max_page_size` (200 افتراضياً). `GET /persons` يدعم
`search`, `generation`, `gender`, `birth_place`, `has_children`, `sort`
و`direction`.

## إخفاء رقم القومى | National-ID masking

`PersonOut.national_id` يظهر كاملاً لـ `editor`/`admin`، ومقنّعاً
(`********0001`) لـ `viewer`. هذا يتم في `PersonOut.from_model`، فلا يمكن
تجاوزه من الـ endpoint.

## سجل التدقيق | Audit log

- **كل** قراءة شخص (`GET /persons/{id}`, `tree`, `relatives`, `relationship`…)
  تكتب `VIEW`، وكل بحث يكتب `SEARCH`.
- الكتابات تكتب `CREATE`/`UPDATE`/`DELETE`/`MERGE`، والاستيراد
  `IMPORT` (بـ `details.stage = upload|preview|mapping|validate|commit`)،
  والتصدير `EXPORT`.
- كل صف يحمل `username` (يُحلّ من `user_id` إن لم تمرره الخدمة)، `ip`، `details`.
- القراءة للمدير فقط: `GET /audit-log` مع فلاتر `action, entity, entity_id,
  user_id, username, date_from, date_to, page, page_size`.

## علاقات القرابة | Relationships

`GET /relationship?a={id}&b={id}` — **متماثل**: نفس الزوج يعطي نفس الجملة
بأي ترتيب.

| الحقل | المعنى |
| --- | --- |
| `relation` | دور الأكبر سناً: «محمد هو جد نور» ⇒ `جد` |
| `relation_from_a` / `relation_from_b` | وصف كل شخص: `جد` / `حفيدة` |
| `generations` | موجب = `a` أكبر سنّاً في السلسلة المباشرة، سالب = العكس، `0` = قرابة جانبية |
| `relation_code` | كود ثابت للطرف الأدنى: `grandchild_f`, `paternal_uncle`, … |
| `common_ancestor_id` / `path` | السلف المشترك الأقرب، والمسار خطوة بخطوة |
| `explanation` | جملة عربية، تبدأ بالأكبر سنّاً والضمير يتبع جنسه |

`GET /persons/{id}/tree?depth=N`:

```json
{"person_id": 9, "up": 3, "down": 4,
 "nodes": [{"id": 1, "full_name": "...", "gender": "M", "birth_date": "1940-03-15", "depth": -2, "generation": "الجد", ...}],
 "links": [{"source": 3, "target": 1, "type": "paternal"}, {"source": 3, "target": 6, "type": "spouse"}]}
```

`depth` سالب للأعلى، `generation` نص عربي للواجهة.

## الاستيراد | Imports

| الخطوة | الطلب | الملاحظات |
| --- | --- | --- |
| 1 | `POST /imports/upload` (multipart `file`) | 201 مع `job` + `preview` (عناوين، أول 20 صفاً، `suggested_mapping`) |
| 2 | `POST /imports/jobs/{id}/mapping` | اختياري: `{mapping: {field: column_index}, linking_mode: none\|by_national_id\|by_name}` |
| 3 | `POST /imports/jobs/{id}/validate` | تقرير `{total_rows, valid_rows, invalid_rows, errors_count, errors[{row, field, value, message, severity}], can_commit}` — بلا كتابة |
| 4 | `POST /imports/jobs/{id}/commit` | `{skip_invalid: bool}` — 200 بحالة `processing`، ثم `GET /imports/jobs/{id}` حتى `completed`/`failed` |
| — | `POST /imports/jobs/{id}/cancel` | إلغاء مهمة `pending`/`ready`، أو إيقاف مهمة قيد التنفيذ عند نهاية الدفعة الحالية (الصفوف المحفوظة تبقى) |

- `row` في الأخطاء = رقم صف الملف (العناوين = 1).
- `linking_mode`:
  - `none` — لا ربط بالأب/الأم.
  - `by_national_id` — يربط بـ `father_national_id`/`mother_national_id`.
  - `by_name` — يربط بالاسم + سنة الميلاد (للملفات القديمة بلا أرقام قومى).
- `GET /imports/template/csv` يعيد قالباً جاهزاً، و`/imports/mapping-templates`
  يحفظ المطابقات المتكررة.
- إن لم يرسل المستخدم مطابقة، تُستخدم المطابقة المقترحة تلقائياً.

## التكرار والدمج | Duplicates and merge

- `GET /duplicates?threshold=0.6` — مجموعات مرشحة: تطابق رقم القومى (مستحيل
  بسبب القيد الفريد) أو الاسم + تاريخ الميلاد، مع ترشيح fuzzy للعربية.
- `GET /duplicates/compare?person_a=&person_b=` — فروق الحقول + درجة التطابق.
- `POST /duplicates/merge` `{target_id, source_id}` (مدير فقط): تنقل العلاقات
  إلى الهدف، وتحوّل المصدر إلى سجل إحالة (`merged_into_id`)، ويكتب سجل
  `MERGE`.

## التصدير | Exports

- `GET /export/persons?format=csv|xlsx` — كل السجلات (أو مُرشَّحة)، مع قناع رقم
  القومى لـ `viewer`.
- `GET /export/tree-csv?person_id=&depth=` — شجرة كـ CSV بأعمدة
  `المعرف, الاسم, الجيل, رقم الأب, رقم الأم, ...`، ويكتب سجل `EXPORT`.

## الأخطاء | Errors

```json
{"detail": "رقم القومى مسجل بالفعل في النظام",
 "errors": [{"field": "national_id", "message": "...", "type": "conflict"}]}
```

| الكود | المعنى |
| --- | --- |
| 400 | خطأ عمل (قواعد العمل، نوع غير معروف، علاقة دورية…) |
| 401 | مصادقة مفقودة/منتهية |
| 403 | صلاحيات غير كافية |
| 404 | غير موجود |
| 409 | تعارض (رقم قومى مكرر) |
| 413 | ملف أو عدد صفوف كبير |
| 422 | فشل تحقق Pydantic (form/JSON) |
| 429 | تجاوز حدّ محاولات الدخول |
| 500 | خطأ داخلي — يُسجَّل ولا تُكشف تفاصيله |