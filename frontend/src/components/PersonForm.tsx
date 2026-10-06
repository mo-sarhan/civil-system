import { useState, type FormEvent } from "react";
import { useAuth } from "../auth/context";
import { api, errorMessage } from "../lib/api";
import type { Person } from "../lib/types";
import PersonPicker from "./PersonPicker";

interface Props {
  person?: Person | null;
  onSaved: (person: Person) => void;
  onCancel: () => void;
}

interface FormState {
  national_id: string;
  full_name: string;
  first_name: string;
  father_name: string;
  grandfather_name: string;
  family_name: string;
  gender: "" | "M" | "F";
  birth_date: string;
  death_date: string;
  birth_place: string;
  father_id: number | null;
  mother_id: number | null;
  notes: string;
}

function toForm(person: Person | null | undefined): FormState {
  return {
    national_id: person?.national_id ?? "",
    full_name: person?.full_name ?? "",
    first_name: person?.first_name ?? "",
    father_name: person?.father_name ?? "",
    grandfather_name: person?.grandfather_name ?? "",
    family_name: person?.family_name ?? "",
    gender: person?.gender ?? "",
    birth_date: person?.birth_date ?? "",
    death_date: person?.death_date ?? "",
    birth_place: person?.birth_place ?? "",
    father_id: person?.father_id ?? null,
    mother_id: person?.mother_id ?? null,
    notes: person?.notes ?? "",
  };
}

/** Nulls out empty strings and empty dates so the API stores real NULLs. */
function toPayload(form: FormState) {
  const clean = (value: string) => (value.trim() === "" ? null : value.trim());
  return {
    national_id: clean(form.national_id),
    full_name: form.full_name.trim(),
    first_name: clean(form.first_name),
    father_name: clean(form.father_name),
    grandfather_name: clean(form.grandfather_name),
    family_name: clean(form.family_name),
    gender: form.gender === "" ? null : form.gender,
    birth_date: form.birth_date || null,
    death_date: form.death_date || null,
    birth_place: clean(form.birth_place),
    father_id: form.father_id,
    mother_id: form.mother_id,
    notes: clean(form.notes),
  };
}

export default function PersonForm({ person, onSaved, onCancel }: Props) {
  const isEdit = Boolean(person);
  const [form, setForm] = useState<FormState>(() => toForm(person));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { user } = useAuth();

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!form.full_name.trim()) {
      setError("الاسم الكامل مطلوب");
      return;
    }
    setBusy(true);
    try {
      const payload = toPayload(form);
      const { data } = isEdit
        ? await api.patch<Person>(`/persons/${person!.id}`, payload)
        : await api.post<Person>("/persons", payload);
      onSaved(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-900">
          {isEdit ? `تعديل بيانات ${person!.full_name}` : "إضافة شخص جديد"}
        </h2>
        <button
          type="button"
          onClick={onCancel}
          className="text-sm text-slate-500 underline hover:text-slate-800"
        >
          إلغاء
        </button>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <label className="block md:col-span-2">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">الاسم الكامل *</span>
          <input
            className="field-input"
            required
            value={form.full_name}
            onChange={(e) => set("full_name", e.target.value)}
            placeholder="مثال: أحمد محمد علي"
          />
        </label>

        <Field
          label="رقم القومى"
          value={form.national_id}
          onChange={(v) => set("national_id", v)}
          ltr
          hint="14 رقماً — يُتحقق منه على الخادم"
        />
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">النوع</span>
          <select
            className="field-input"
            value={form.gender}
            onChange={(e) => set("gender", e.target.value as FormState["gender"])}
          >
            <option value="">غير محدد</option>
            <option value="M">ذكر</option>
            <option value="F">أنثى</option>
          </select>
        </label>

        <Field label="الاسم الأول" value={form.first_name} onChange={(v) => set("first_name", v)} />
        <Field label="اسم الأب" value={form.father_name} onChange={(v) => set("father_name", v)} />
        <Field label="اسم الجد" value={form.grandfather_name} onChange={(v) => set("grandfather_name", v)} />
        <Field label="اللقب" value={form.family_name} onChange={(v) => set("family_name", v)} />

        <Field label="تاريخ الميلاد" type="date" value={form.birth_date} onChange={(v) => set("birth_date", v)} ltr />
        <Field label="تاريخ الوفاة" type="date" value={form.death_date} onChange={(v) => set("death_date", v)} ltr />
        <Field label="محل الميلاد" value={form.birth_place} onChange={(v) => set("birth_place", v)} />

        <PersonPicker
          label="الأب"
          value={form.father_id}
          onChange={(person) => set("father_id", person?.id ?? null)}
        />
        <PersonPicker
          label="الأم"
          value={form.mother_id}
          onChange={(person) => set("mother_id", person?.id ?? null)}
        />

        <label className="block md:col-span-2">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">ملاحظات</span>
          <textarea
            className="field-input min-h-24"
            value={form.notes}
            onChange={(e) => set("notes", e.target.value)}
          />
        </label>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          type="submit"
          disabled={busy || (user?.role === "viewer")}
          className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {busy ? "جارٍ الحفظ…" : isEdit ? "حفظ التعديلات" : "إضافة الشخص"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          إلغاء
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  ltr,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  ltr?: boolean;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <input
        type={type}
        className={`field-input ${ltr ? "ltr" : ""}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
    </label>
  );
}
