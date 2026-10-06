import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/context";
import { api, errorMessage } from "../lib/api";
import type { Marriage, MarriageStatus, Page } from "../lib/types";

const STATUS_LABELS: Record<string, string> = {
  married: "ساري",
  divorced: "مطلق",
  widowed: "أرمل",
  separated: "منفصل",
};

interface FormState {
  husband_id: string;
  wife_id: string;
  start_date: string;
  end_date: string;
  status: MarriageStatus;
  notes: string;
}

export default function MarriagesPage() {
  const { user } = useAuth();
  const canWrite = user?.role === "editor" || user?.role === "admin";
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Marriage | null>(null);

  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status) params.set("status", status);

  const { data, isPending, error } = useQuery({
    queryKey: ["marriages", params.toString()],
    queryFn: async () => {
      const { data } = await api.get<Page<Marriage>>(`/marriages?${params.toString()}`);
      return data;
    },
    placeholderData: (previous) => previous,
  });

  const saveMutation = useMutation({
    mutationFn: async (body: FormState & { id?: number }) => {
      const payload = {
        ...body,
        husband_id: Number(body.husband_id),
        wife_id: Number(body.wife_id),
        start_date: body.start_date || null,
        end_date: body.end_date || null,
      };
      if (body.id) {
        const { data } = await api.patch<Marriage>(`/marriages/${body.id}`, {
          start_date: payload.start_date,
          end_date: payload.end_date,
          status: payload.status,
          notes: body.notes || null,
        });
        return data;
      }
      const { data } = await api.post<Marriage>("/marriages", payload);
      return data;
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["marriages"] }),
        queryClient.invalidateQueries({ queryKey: ["persons"] }),
        queryClient.invalidateQueries({ queryKey: ["stats"] }),
      ]);
      setCreating(false);
      setEditing(null);
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (id: number) => api.delete(`/marriages/${id}`),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["marriages"] }),
        queryClient.invalidateQueries({ queryKey: ["persons"] }),
      ]);
    },
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">سجلات الزواج</h1>
          <p className="mt-1 text-sm text-slate-500">
            {data ? `${data.total.toLocaleString("ar-EG")} زواج` : " "}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="field-input w-36"
          >
            <option value="">الحالة: الكل</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {canWrite && !creating && !editing && (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
            >
              تسجيل زواج
            </button>
          )}
        </div>
      </header>

      {saveMutation.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(saveMutation.error)}
        </div>
      )}
      {removeMutation.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(removeMutation.error)}
        </div>
      )}

      {(creating || editing) && (
        <MarriageForm
          key={editing?.id ?? "new"}
          initial={editing}
          busy={saveMutation.isPending}
          onSubmit={(form) => saveMutation.mutate({ ...form, id: editing?.id })}
          onCancel={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 text-start font-semibold">الزوج</th>
              <th className="px-4 py-3 text-start font-semibold">الزوجة</th>
              <th className="ltr px-4 py-3 text-start font-semibold">البداية</th>
              <th className="ltr px-4 py-3 text-start font-semibold">النهاية</th>
              <th className="px-4 py-3 text-start font-semibold">الحالة</th>
              <th className="px-4 py-3 text-end font-semibold">إجراءات</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isPending && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-slate-400">
                  جارٍ التحميل…
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-red-600">
                  {errorMessage(error)}
                </td>
              </tr>
            )}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-slate-400">
                  لا توجد زيجات مطابقة
                </td>
              </tr>
            )}
            {data?.items.map((marriage) => (
              <tr key={marriage.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  {marriage.husband_id ? (
                    <Link to={`/persons/${marriage.husband_id}`} className="text-slate-800 hover:underline">
                      {marriage.husband_name ?? `#${marriage.husband_id}`}
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-4 py-3">
                  {marriage.wife_id ? (
                    <Link to={`/persons/${marriage.wife_id}`} className="text-slate-800 hover:underline">
                      {marriage.wife_name ?? `#${marriage.wife_id}`}
                    </Link>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="ltr px-4 py-3 text-slate-600">{marriage.start_date ?? "—"}</td>
                <td className="ltr px-4 py-3 text-slate-600">{marriage.end_date ?? "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={marriage.status} />
                </td>
                <td className="px-4 py-3 text-end">
                  {canWrite && (
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(marriage);
                        setCreating(false);
                      }}
                      className="text-sm text-slate-600 underline hover:text-slate-900"
                    >
                      تعديل
                    </button>
                  )}
                  {isAdmin && (
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm("حذف سجل الزواج نهائياً؟")) removeMutation.mutate(marriage.id);
                      }}
                      className="ms-3 text-sm text-red-600 underline hover:text-red-700"
                    >
                      حذف
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <button
            type="button"
            disabled={data.page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 disabled:opacity-40"
          >
            السابق
          </button>
          <span>
            صفحة {data.page} من {data.pages}
          </span>
          <button
            type="button"
            disabled={data.page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 disabled:opacity-40"
          >
            التالي
          </button>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tones: Record<string, string> = {
    married: "bg-emerald-50 text-emerald-700 border-emerald-200",
    divorced: "bg-slate-50 text-slate-600 border-slate-200",
    widowed: "bg-slate-100 text-slate-600 border-slate-300",
    separated: "bg-amber-50 text-amber-700 border-amber-200",
  };
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs ${tones[status] ?? tones.married}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function MarriageForm({
  initial,
  busy,
  onSubmit,
  onCancel,
}: {
  initial: Marriage | null;
  busy: boolean;
  onSubmit: (form: FormState) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<FormState>({
    husband_id: initial ? String(initial.husband_id) : "",
    wife_id: initial ? String(initial.wife_id) : "",
    start_date: initial?.start_date ?? "",
    end_date: initial?.end_date ?? "",
    status: (initial?.status as MarriageStatus) ?? "married",
    notes: initial?.notes ?? "",
  });

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
      className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-900">
          {initial ? `تعديل الزواج #${initial.id}` : "تسجيل زواج جديد"}
        </h2>
        <button type="button" onClick={onCancel} className="text-sm text-slate-500 underline hover:text-slate-800">
          إلغاء
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">رقم الزوج *</span>
          <input
            required
            type="number"
            min={1}
            className="field-input ltr"
            value={form.husband_id}
            disabled={Boolean(initial)}
            onChange={(e) => set("husband_id", e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">رقم الزوجة *</span>
          <input
            required
            type="number"
            min={1}
            className="field-input ltr"
            value={form.wife_id}
            disabled={Boolean(initial)}
            onChange={(e) => set("wife_id", e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">تاريخ البداية</span>
          <input
            type="date"
            className="field-input ltr"
            value={form.start_date}
            onChange={(e) => set("start_date", e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">تاريخ النهاية</span>
          <input
            type="date"
            className="field-input ltr"
            value={form.end_date}
            onChange={(e) => set("end_date", e.target.value)}
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">الحالة</span>
          <select
            className="field-input"
            value={form.status}
            onChange={(e) => set("status", e.target.value as MarriageStatus)}
          >
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="block md:col-span-2">
          <span className="mb-1.5 block text-sm font-medium text-slate-700">ملاحظات</span>
          <textarea className="field-input min-h-20" value={form.notes} onChange={(e) => set("notes", e.target.value)} />
        </label>
      </div>

      <div className="mt-5 flex gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {busy ? "جارٍ الحفظ…" : initial ? "حفظ التعديلات" : "تسجيل الزواج"}
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