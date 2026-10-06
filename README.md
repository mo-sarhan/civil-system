# نظام السجل المدني وشجرة العائلة | Civil Registry & Family Tree

نظام متكامل لإدارة سجلات الأحوال المدنية مع محرك شجرة عائلة كامل، مبنيّ
للتعامل مع الأسماء العربية بشكل صحيح (RTL، تطبيع النص، إخفاء رقم القومى،
وسجل تدقيق كامل).

An Arabic-first (RTL) civil-registry backend with a full family-tree engine:
Arabic-aware name handling, national-ID validation, duplicate detection,
imports/exports and a complete audit trail.

---

## المحتويات | Contents

- [المزايا | Features](#المزايا--features)
- [التقنيات | Stack](#التقنيات--stack)
- [التشغيل السريع | Quick start](#التشغيل-السريع--quick-start)
- [التطوير المحلي | Local development](#التطوير-المحلي--local-development)
- [الأوامر | Make targets](#الأوامر--make-targets)
- [الأدوار والصلاحيات | Roles](#الأدوار-والصلاحيات--roles)
- [واجهة الـ API | API surface](#واجهة-الـ-api--api-surface)
- [الاختبارات | Tests](#الاختبارات--tests)
- [بنية المشروع | Repository layout](#بنية-المشروع--repository-layout)
- [المزيد من التوثيق | Further documentation](#المزيد-من-التوثيق--further-documentation)

## المزايا | Features

| المجال | التفاصيل |
| --- | --- |
| السجلات | إنشاء وتعديل وحذف الأشخاص، تحقق كامل من رقم القومى (14 رقماً: الجيل، تاريخ الميلاد، النوع)، وحد أدنى 12 سنة بين الوالد والابن. |
| القرابة | الوالدون، الأبناء، الإخوة، الأزواج، الأجداد، الأحفاد، الأعمام والخالات ( paternal/maternal)، النظراء، أبناء الإخوة، والعلاقات بالأصهار. |
| شجرة العائلة | شجرة كاملة `up`/`down` بعمق محدود، مع تصدير CSV للشجرة. |
| الاستيراد | CSV/XLSX على أربع مراحل (رفع ← معاينة ومطابقة الأعمدة ← تحقق ← تنفيذ)، قوالب مطابقة محفوظة، وتقارير أخطاء بالعربية سطراً بسطر. |
| التصدير | CSV و XLSX للأشخاص ولشجرة العائلة، مع إخفاء رقم القومى حسب الدور. |
| جودة البيانات | كشف التكرار (تطابق رقم القومى أو الاسم مع تاريخ الميلاد، مع ترشيح fuzzy للنصوص العربية) ودمج السجلات. |
| الإحصاءات | إجماليات، توزيع الجنسين، الأجيال، أماكن الميلاد، أكبر العائلات، ومؤشرات جودة البيانات. |
| الأمان | JWT (وصول + تجديد)، Argon2، قفل الحساب بعد محاولات فاشلة، أدوار، CORS، ورؤوس أمان. |
| التدقيق | تسجيل كل قراءة/كتابة/تصدير/استيراد مع اسم المستخدم وعنوان IP والوقت. |

## التقنيات | Stack

- **الخلفية | Backend:** Python 3.12، FastAPI، SQLAlchemy 2، Alembic، Pydantic v2، PostgreSQL 16.
- **الأدوات | Tooling:** pytest، ruff، black، Docker Compose، Make، GitHub Actions.
- **الواجهة | Frontend:** React + TypeScript + Vite + Tailwind + TanStack Query + D3 (قيد الإنشاء — لم تبدأ بعد).

## التشغيل السريع | Quick start

باستخدام Docker Compose:

```bash
cp .env.example .env      # or: make env  (generates a random SECRET_KEY)
make up                   # builds and starts PostgreSQL + the API
make seed-docker          # loads sample_civil_registry.sql and creates the admin
open http://localhost:8000/docs
```

> كلمة مرور المدير تُطبع مرة واحدة فقط أثناء `seed` — احتفظ بها، ويجب
> تغييرها عند أول تسجيل دخول.

With Docker Compose:

```bash
cp .env.example .env      # or: make env  (generates a random SECRET_KEY)
make up                   # builds and starts PostgreSQL + the API
make seed-docker          # loads sample_civil_registry.sql and creates the admin
open http://localhost:8000/docs
```

> The bootstrap admin password is printed once during `seed`; change it at the
> first login.

المتغيرات المهمة في `.env`: `SECRET_KEY` (إجباري — يوقف التشغيل إن كان مفقوداً)،
`POSTGRES_*`، `CORS_ORIGINS`، `MASK_NATIONAL_ID_ROLES`.

## التطوير المحلي | Local development

```bash
make install              # virtualenv + backend dependencies
make db-up                # PostgreSQL 16 in Docker (published on 5432)
make test-db              # create civil_registry_test
make migrate              # alembic upgrade head
make seed                 # sample data + bootstrap admin
make dev                  # uvicorn --reload on :8000
```

خارج Docker، انسخ `backend/.env.local.example` إلى `backend/.env.local` وعدّل
`POSTGRES_HOST`/`POSTGRES_PORT`. ملف `.env.local` مستبعد من git.

## الأوامر | Make targets

| الأمر | الوظيفة |
| --- | --- |
| `make help` | عرض كل الأوامر |
| `make install` | إنشاء بيئة بايثون افتراضية وتثبيت الاعتماديات |
| `make up` / `make down` | تشغيل / إيقاف الحاويات |
| `make build` | بناء الصور |
| `make logs` | متابعة السجلات |
| `make migrate` / `make migrate-docker` | تطبيق الترحيلات |
| `make seed` / `make seed-docker` | تحميل البيانات التجريبية والمدير |
| `make test` / `make test-cov` | تشغيل الاختبارات / مع تقرير التغطية |
| `make lint` / `make format` | ruff + black |
| `make check` | lint + test |
| `make shell` / `make psql` | صدفة SQL داخل الحاوية / على قاعدة التطوير |
| `make secret` | توليد `SECRET_KEY` قوي |
| `make clean` | إيقاف الحاويات وحذف الأحجام |

## الأدوار والصلاحيات | Roles

| الدور | الصلاحيات |
| --- | --- |
| `viewer` | قراءة السجلات والعلاقات مع إخفاء رقم القومى (آخر 4 أرقام). |
| `editor` | كل صلاحيات القراءة + الإضافة والتعديل والحذف العادي والاستيراد والتصدير. |
| `admin` | كل ما سبق + إدارة المستخدمين، دمج السجلات، وقراءة سجل التدقيق. |

## واجهة الـ API | API surface

كل المسارات تحت `/api/v1`، والتوثيق التفاعلي على `/docs`:

| المجموعة | المسارات |
| --- | --- |
| المصادقة | `POST /auth/login`، `POST /auth/refresh`، `GET /auth/me`، `POST /auth/change-password` |
| الأشخاص | `GET/POST /persons`، `GET/PATCH/DELETE /persons/{id}`، `GET /persons/search`، `GET /persons/{id}/family-summary` |
| القرابة | `/persons/{id}/parents`، `children`، `siblings`، `spouses`، `ancestors`، `descendants`، `relatives`، `tree`، `GET /relationship?a=&b=` |
| الزواج | `GET/POST /marriages`، `PATCH/DELETE /marriages/{id}` |
| التكرار | `GET /duplicates`، `GET /duplicates/compare`، `POST /duplicates/merge` |
| الاستيراد | `/imports/upload`، `/imports/jobs/{id}/preview`، `/mapping`، `/validate`، `/commit`، `/cancel`، `/imports/mapping-templates` |
| التصدير | `GET /export/persons`، `GET /export/tree-csv` |
| الإحصاءات | `GET /stats`، `/stats/generations`، `/stats/birth-places`، `/stats/birth-years`، `/stats/largest-families`، `/stats/missing-links`، `/stats/data-quality` |
| التدقيق | `GET /audit-log`، `/audit-log/actions`، `/audit-log/export` |
| النظام | `GET /health`، `GET /config`، `GET/POST /users` |

## الاختبارات | Tests

```bash
make test         # 212 tests against a real PostgreSQL (civil_registry_test)
make test-cov     # same suite with a branch-coverage report (81.1%)
```

الاختبارات تشغّل ترحيلات Alembic مرة واحدة لكل جلسة ثم تمسح الجداول قبل كل
اختبار، وتستخدم عينة `sample_civil_registry.sql` الحقيقية. CI يشغّلها مع
`--cov=app` ويُسقطها إذا نزلت التغطية تحت 80%.

## بنية المشروع | Repository layout

```
.
├── backend/            FastAPI app (app/api, app/services, app/models), migrations, tests
├── frontend/           React + TypeScript UI (not started yet)
├── scripts/db-init/    PostgreSQL init SQL for Compose
├── docs/               architecture, API notes, decisions
├── sample_civil_registry.sql   14 people / 5 marriages sample data
├── docker-compose.yml  db + backend (+ frontend later)
├── Makefile            every workflow command
└── .env.example        all settings, no secrets
```

## المزيد من التوثيق | Further documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — الطبقات، نموذج البيانات، محرّك القرابة.
- [docs/API.md](docs/API.md) — ملخص الاستجابات والعقود المهمة.
- [docs/DECISIONS.md](docs/DECISIONS.md) — القرارات الهندسية والقرارات غير الواضحة.
- `http://localhost:8000/docs` — مرجع OpenAPI التفاعلي.

---

نظام السجل المدني — بيانات شخصية حساسة: كل الوصول للبيانات يكتب سجل تدقيق.
Civil-registry data is sensitive: every read of personal data is audited.