import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../auth/context";
import { api, errorMessage } from "../lib/api";
import type { AuditActions, AuditEntry, AuditSummary, Page } from "../lib/types";

const ACTION_LABELS: Record<string, string> = {
  CREATE: "إنشاء",
  UPDATE: "تعديل",
  DELETE: "حذف",
  VIEW: "عرض",
  LOGIN: "دخول",
  LOGOUT: "خروج",
  IMPORT: "استيراد",
  EXPORT: "تصدير",
  MERGE: "دمج",
  ROLE_CHANGE: "تغيير دور",
  PASSWORD_CHANGE: "تغيير كلمة مرور",
  UNLOCK: "فك قفل",
  OTHER: "أخرى",
};

export default function AuditPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [username, setUsername] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const params = new URLSearchParams({ page: String(page), page_size: "50" });
  if (action) params.set("action", action);
  if (entity) params.set("entity", entity);
  if (username) params.set("username", username);
  if (dateFrom) params.set("date_from", `${dateFrom}T00:00:00`);
  if (dateTo) params.set("date_to", `${dateTo}T23:59:59`);

  const { data, isPending, error } = useQuery({
    queryKey: ["audit", params.toString()],
    queryFn: async () => {
      const { data } = await api.get<Page<AuditEntry>>(`/audit-log?${params.toString()}`);
      return data;
    },
    enabled: isAdmin,
  });

  const actionsQuery = useQuery({
    queryKey: ["audit-actions"],
    queryFn: async () => {
      const { data } = await api.get<AuditActions>("/audit-log/actions");
      return data;
    },
    enabled: isAdmin,
  });

  const summaryQuery = useQuery({
    queryKey: ["audit-summary"],
    queryFn: async () => {
      const { data } = await api.get<AuditSummary>("/audit-log/export");
      return data;
    },
    enabled: isAdmin,
  });

  if (!isAdmin) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white px-6 py-10 text-center text-sm text-slate-500">
        سجل التدقيق متاح للمدير فقط.
      </div>
    );
  }

  const summary = summaryQuery.data;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">سجل التدقيق</h1>
        <p className="mt-1 text-sm text-slate-500">{summary ? `إجمالي ${summary.total.toLocaleString("ar-EG")} عملية` : " "}</p>
      </header>

      {summary && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-bold text-slate-900">العمليات حسب النوع</h2>
            <div className="space-y-2">
              {summary.by_action.slice(0, 8).map((entry) => (
                <div key={entry.action} className="flex items-center justify-between text-sm">
                  <span className="text-slate-600">{ACTION_LABELS[entry.action] ?? entry.action}</span>
                  <span className="ltr font-semibold text-slate-800">{entry.count.toLocaleString("ar-EG")}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-bold text-slate-900">المستخدمون الأكثر نشاطاً</h2>
            <div className="space-y-2">
              {summary.top_users.length === 0 && <p className="text-sm text-slate-400">لا توجد بيانات</p>}
              {summary.top_users.map((entry) => (
                <div key={entry.username} className="flex items-center justify-between text-sm">
                  <span className="ltr text-slate-600">{entry.username}</span>
                  <span className="ltr font-semibold text-slate-800">{entry.count.toLocaleString("ar-EG")}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-bold text-slate-900">آخر عملية</h2>
            <p className="text-sm text-slate-600">{summary.latest ? new Date(summary.latest).toLocaleString("ar-EG") : "—"}</p>
          </section>
        </div>
      )}

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">النوع</span>
            <select className="field-input" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
              <option value="">الكل</option>
              {(actionsQuery.data?.actions ?? []).map((a) => (
                <option key={a} value={a}>{ACTION_LABELS[a] ?? a}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">الكيان</span>
            <select className="field-input" value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1); }}>
              <option value="">الكل</option>
              {(actionsQuery.data?.entities ?? []).map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">اسم المستخدم</span>
            <input className="field-input ltr" value={username} onChange={(e) => { setUsername(e.target.value); setPage(1); }} placeholder="…" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">من تاريخ</span>
            <input type="date" className="field-input ltr" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-600">إلى تاريخ</span>
            <input type="date" className="field-input ltr" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1); }} />
          </label>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 text-start font-semibold">التاريخ</th>
              <th className="px-4 py-3 text-start font-semibold">المستخدم</th>
              <th className="px-4 py-3 text-start font-semibold">العملية</th>
              <th className="px-4 py-3 text-start font-semibold">الكيان</th>
              <th className="ltr px-4 py-3 text-start font-semibold">العنوان</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isPending && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-400">جارٍ التحميل…</td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-red-600">{errorMessage(error)}</td>
              </tr>
            )}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-400">لا توجد عمليات مطابقة</td>
              </tr>
            )}
            {data?.items.map((entry) => (
              <tr key={entry.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-slate-600">{formatDate(entry.created_at)}</td>
                <td className="ltr px-4 py-3 text-slate-800">{entry.username ?? "—"}</td>
                <td className="px-4 py-3">
                  <ActionBadge action={entry.action} />
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {entry.entity ?? "—"}
                  {entry.entity_id && <span className="ltr ms-1 text-slate-400">#{entry.entity_id}</span>}
                </td>
                <td className="ltr px-4 py-3 text-xs text-slate-500">{entry.ip ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <button type="button" disabled={data.page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 disabled:opacity-40">
            السابق
          </button>
          <span>صفحة {data.page} من {data.pages}</span>
          <button type="button" disabled={data.page >= data.pages} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 disabled:opacity-40">
            التالي
          </button>
        </div>
      )}
    </div>
  );
}

function ActionBadge({ action }: { action: string }) {
  const tones: Record<string, string> = {
    CREATE: "border-emerald-200 bg-emerald-50 text-emerald-700",
    UPDATE: "border-sky-200 bg-sky-50 text-sky-700",
    DELETE: "border-red-200 bg-red-50 text-red-600",
    LOGIN: "border-slate-200 bg-slate-100 text-slate-600",
    IMPORT: "border-amber-200 bg-amber-50 text-amber-700",
    EXPORT: "border-purple-200 bg-purple-50 text-purple-700",
    MERGE: "border-orange-200 bg-orange-50 text-orange-700",
  };
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs ${tones[action] ?? "border-slate-200 bg-slate-50 text-slate-600"}`}>
      {ACTION_LABELS[action] ?? action}
    </span>
  );
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "medium" });
}