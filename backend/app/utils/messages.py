"""Arabic error messages.

Keeping every user-facing message in one module makes it easy to review the
wording of validation errors and keeps services free of long Arabic literals.
"""

from __future__ import annotations


class Messages:
    """Arabic messages returned by validators and services."""

    NATIONAL_ID_LENGTH = "رقم القومى يجب أن يتكون من 14 رقماً"
    NATIONAL_ID_DIGITS_ONLY = "رقم القومى يجب أن يحتوي على أرقام فقط"
    NATIONAL_ID_CENTURY = (
        "الرقم الأول من رقم القومى يجب أن يكون 2 للجيل الأول (1900-1999) "
        "أو 3 للجيل الثاني (2000-2099)"
    )
    NATIONAL_ID_DATE = "تاريخ الميلاد المدوّن في رقم القومى غير صحيح"
    NATIONAL_ID_DATE_INVALID = "الرقم 2 إلى 7 من رقم القومى يجب أن تمثل تاريخ ميلاد صحيح"
    NATIONAL_ID_GENDER = (
        "رقم القومى لا يتوافق مع النوع: الرقم 13 يجب أن يكون فردياً للذكور " "زوجياً للإناث"
    )
    NATIONAL_ID_DUPLICATE = "رقم القومى مسجل بالفعل في النظام"
    NATIONAL_ID_MISMATCH_DATE = "تاريخ الميلاد المسجل لا يطابق تاريخ الميلاد المدوّن في رقم القومى"
    FULL_NAME_REQUIRED = "الاسم الكامل مطلوب"
    GENDER_INVALID = "النوع يجب أن يكون M للذكور أو F للإناث"
    BIRTH_IN_FUTURE = "تاريخ الميلاد لا يمكن أن يكون في المستقبل"
    DEATH_BEFORE_BIRTH = "تاريخ الوفاة يجب أن يكون بعد تاريخ الميلاد أو مساوياً له"
    DEATH_IN_FUTURE = "تاريخ الوفاة لا يمكن أن يكون في المستقبل"

    FATHER_MUST_BE_MALE = "الوالد يجب أن يكون ذكراً"
    MOTHER_MUST_BE_FEMALE = "الوالدة يجب أن تكون أنثى"
    PARENT_NOT_FOUND = "الوالد أو الوالدة غير موجود في النظام"
    PARENT_SELF = "لا يمكن أن يكون الشخص والداً أو والدة لنفسه"
    PARENT_CYCLE = (
        "العلاقة المحددة تُنتج حلقة في شجرة العائلة: لا يمكن أن يكون الشخص سلفاً أو نسلاً لنفسه"
    )
    PARENT_TOO_YOUNG = (
        "يجب أن يكون عمر الوالد {actual} سنة على الأقل عند ميلاد الابن (الحد الأدنى {required} سنة)"
    )
    PARENT_AGE_UNKNOWN = "لا يمكن التحقق من فارق العمر: تاريخ ميلاد الوالد غير مسجل"
    PARENT_DIED_BEFORE_CHILD = "تاريخ وفاة الوالد سابق لتاريخ ميلاد الابن"
    CHILD_BEFORE_PARENT_MARRIAGE = "تاريخ ميلاد الابن سابق لتاريخ زواج الوالدين"

    ALREADY_MERGED = "هذا السجل تم دمجه مسبقاً مع سجل آخر"
    SELF_MERGE = "لا يمكن دمج السجل مع نفسه"
    MERGE_TARGET_MERGED = "السجل الهدف مدموج بالفعل، اختر السجل النشط"
    PERSON_NOT_FOUND = "السجل غير موجود"
    MARRIAGE_NOT_FOUND = "بيانات الزواج غير موجودة"
    MARRIAGE_PARTNERS_GENDER = "الزوج يجب أن يكون ذكراً والزوجة أنثى"
    MARRIAGE_DUPLICATE = "يوجد تسجيل زواج بين نفس الزوجين"
    MARRIAGE_END_BEFORE_START = "تاريخ انتهاء الزواج يجب أن يكون بعد تاريخ البداية"
    MARRIAGE_SAME_PERSON = "لا يمكن تسجيل زواج بين الشخص ونفسه"

    UNAUTHORIZED = "يجب تسجيل الدخول للمتابعة"
    INVALID_CREDENTIALS = "اسم المستخدم أو كلمة المرور غير صحيحة"
    ACCOUNT_DISABLED = "هذا الحساب معطّل، راجع مدير النظام"
    ACCOUNT_LOCKED = "تم قفل الحساب مؤقتاً بسبب محاولات دخول فاشلة متكررة"
    FORBIDDEN = "لا تملك الصلاحية اللازمة لتنفيذ هذا الإجراء"
    USERNAME_TAKEN = "اسم المستخدم مستخدم بالفعل"
    USER_NOT_FOUND = "المستخدم غير موجود"
    PASSWORD_TOO_SHORT = "كلمة المرور يجب أن تكون 12 حرفاً على الأقل"
    PASSWORD_SAME_AS_OLD = "كلمة المرور الجديدة يجب أن تختلف عن القديمة"
    WEAK_PASSWORD = "كلمة المرور ضعيفة: يجب أن تحتوي على حرف كبير وحرف صغير ورقم"
    CANNOT_DELETE_SELF = "لا يمكنك حذف حسابك الحالي"
    CANNOT_DEMOTE_SELF = "لا يمكنك تغيير صلاحيات حسابك الحالي"

    IMPORT_FILE_EMPTY = "الملف فارغ أو لا يحتوي على بيانات"
    IMPORT_UNSUPPORTED_TYPE = "نوع الملف غير مدعوم، الصيغ المسموحة: CSV أو XLSX"
    IMPORT_NO_MAPPING = "يجب تحديد مطابقة أعمدة الملف أولاً"
    IMPORT_MAPPING_INVALID = "عدد الأعمدة في المطابقة يجب أن يطابق أعمدة الملف"
    IMPORT_JOB_NOT_FOUND = "مهمة الاستيراد غير موجودة"
    IMPORT_INVALID_STATUS = "لا يمكن تنفيذ هذه الخطوة في الحالة الحالية للمهمة"
    IMPORT_LINK_AMBIGUOUS = "تعدد الامتدادات: يوجد أكثر من شخص بنفس الاسم"
    IMPORT_LINK_NOT_FOUND = "لم يتم العثور على الأب/الأم المحدد بالاسم"

    DUPLICATE_NOT_FOUND = "لم يتم العثور على سجلات مكررة"
    EXPORT_TOO_LARGE = "عدد السجلات كبير جداً للتصدير، يرجى تضييق عوامل التصفية"
