import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../lib/api";

interface Options {
  q: string;
  gender: string;
  birth_year_from: string;
  birth_year_to: string;
  birth_place: string;
  limit: string;
}

export default function ExportsPage() {
  const [options, setOptions] = useState<Options>({
    q: "",
    gender: "",
    birth_year_from: "",
    birth_year_to: "",
    birth_place: "",
    limit: "10000",
  });
  const [personId, setPersonId] = useState("");
  const [up, setUp] = useState(3);
  const [down, setDown] = useState(4);

  const set = <K extends keyof Options>(key: K, value: Options[K]) =>
    setOptions((prev) => ({ ...prev, [key]: value }));

  const downloadMutation = useMutation({
    mutationFn: async ({ format }: { format: "csv" | "xlsx" }) => {
      const params = new URLSearchParams();
      if (options.q) params.set("q", options.q);
      if (options.gender) params.set("gender", options.gender);
      if (options.birth_year_from) params.set("birth_year_from", options.birth_year_from);
      if (options.birth_year_to) params.set("birth_year_to", options.birth_year_to);
      if (options.birth_place) params.set("birth_place", options.birth_place);
      params.set("limit", options.limit || "10000");
      params.set("format", format);
      const { data, headers } = await api.get(`/export/persons?${params.toString()}`, {
        responseType: "blob",
      });
      saveBlob(data, inferFilename(headers) ?? `civil_registry_export.${format}`);
    },
  });

  const treeMutation = useMutation({
    mutationFn: async () => {
      const qs = new URLSearchParams({ person_id: personId, up: String(up), down: String(down) });
      const { data, headers } = await api.get(`/export/tree-csv?${qs.toString()}`, {
        responseType: "blob",
      });
      saveBlob(data, inferFilename(headers) ?? `tree_${personId}.csv`);
    },
    onSettled: () => setPersonId(""),
  });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">تصدير البيانات</h1>
        <p className="mt-1 text-sm text-slate-500">تنزيل ملفات CSV أو Excel بترميز UTF-8 يدعم العربية</p>
      </header>

      {downloadMutation.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          تعذر التصدير ({String((downloadMutation.error as Error)?.message ?? "")})
        </div>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-bold text-slate-900">السجلات المطابقة لشروط البحث</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <label className="block md:col-span-2">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">بحث بالاسم</span>
            <input className="field-input" value={options.q} onChange={(e) => set("q", e.target.value)} placeholder="اسم أو جزء من الاسم" />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">الجنس</span>
            <select className="field-input" value={options.gender} onChange={(e) => set("gender", e.target.value)}>
              <option value="">الكل</option>
              <option value="M">ذكر</option>
              <option value="F">أنثى</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">تاريخ الميلاد من</span>
            <input type="number" min={1900} max={2100} className="field-input ltr" value={options.birth_year_from} onChange={(e) => set("birth_year_from", e.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">تاريخ الميلاد إلى</span>
            <input type="number" min={1900} max={2100} className="field-input ltr" value={options.birth_year_to} onChange={(e) => set("birth_year_to", e.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">محل الميلاد</span>
            <input className="field-input" value={options.birth_place} onChange={(e) => set("birth_place", e.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">الحد الأقصى للصفوف</span>
            <input type="number" min={1} max={500000} className="field-input ltr" value={options.limit} onChange={(e) => set("limit", e.target.value)} />
          </label>
        </div>
        <div className="mt-5 flex gap-3">
          <button
            type="button"
            disabled={downloadMutation.isPending}
            onClick={() => downloadMutation.mutate({ format: "csv" })}
            className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {downloadMutation.isPending ? "جارٍ التصدير…" : "تنزيل CSV"}
          </button>
          <button
            type="button"
            disabled={downloadMutation.isPending}
            onClick={() => downloadMutation.mutate({ format: "xlsx" })}
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            تنزيل Excel
          </button>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-base font-bold text-slate-900">شجرة شخص واحد (CSV)</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">رقم الشخص *</span>
            <input required type="number" min={1} className="field-input ltr" value={personId} onChange={(e) => setPersonId(e.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">أجيال الأجداد (الأعلى)</span>
            <input type="number" min={0} max={10} className="field-input ltr" value={up} onChange={(e) => setUp(Number(e.target.value))} />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-700">أجيال الأحفاد (الأدنى)</span>
            <input type="number" min={0} max={10} className="field-input ltr" value={down} onChange={(e) => setDown(Number(e.target.value))} />
          </label>
        </div>
        <button
          type="button"
          disabled={!personId || treeMutation.isPending}
          onClick={() => treeMutation.mutate()}
          className="mt-5 rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {treeMutation.isPending ? "جارٍ التصدير…" : "تنزيل الشجرة"}
        </button>
      </section>
    </div>
  );
}

function inferFilename(headers: Record<string, unknown>): string | null {
  const disposition = headers["content-disposition"] as string | undefined;
  const match = /filename="?([^";]+)"?/.exec(disposition ?? "");
  return match ? match[1] : null;
}

function saveBlob(data: Blob, filename: string): void {
  const url = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}