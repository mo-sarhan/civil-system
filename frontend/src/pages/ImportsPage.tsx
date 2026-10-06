import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useAuth } from "../auth/context";
import { api, errorMessage } from "../lib/api";
import type {
  ImportError,
  ImportPreview,
  ImportJob,
  ImportValidationReport,
  MappingTemplate,
  Page,
} from "../lib/types";

const STATUS_LABELS: Record<string, string> = {
  pending: "في الانتظار",
  validating: "جارٍ التحقق",
  ready: "جاهز للاستيراد",
  processing: "جارٍ الاستيراد",
  completed: "اكتمل",
  failed: "فشل",
  cancelled: "ملغى",
};

const EMPTY_REPORT: ImportValidationReport = {
  job_id: 0,
  status: "",
  total_rows: 0,
  valid_rows: 0,
  invalid_rows: 0,
  errors_count: 0,
  warnings_count: 0,
  errors: [],
  errors_truncated: false,
  linking_mode: "none",
  can_commit: false,
};

function isActive(status: string): boolean {
  return status === "pending" || status === "validating" || status === "processing";
}

function toNumber(mapping: Record<string, string>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [field, value] of Object.entries(mapping)) {
    if (value !== "" && value !== "__none__") out[field] = Number(value);
  }
  return out;
}

function deriveInitialMapping(preview: ImportPreview): Record<string, string> {
  const initial: Record<string, string> = {};
  for (const [field, col] of Object.entries(preview.suggested_mapping ?? {})) {
    initial[field] = String(col);
  }
  return initial;
}

export default function ImportsPage() {
  const { user } = useAuth();
  const canImport = user?.role === "editor" || user?.role === "admin";

  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [linkingMode, setLinkingMode] = useState("none");
  const [job, setJob] = useState<ImportJob | null>(null);
  const [report, setReport] = useState<ImportValidationReport>(EMPTY_REPORT);
  const [fileInputKey, setFileInputKey] = useState(0);

  if (!canImport) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white px-6 py-10 text-center text-sm text-slate-500">
        استيراد الملفات متاح للمحرر والمدير فقط.
      </div>
    );
  }

  const startFresh = (job: ImportJob, p: ImportPreview) => {
    setPreview(p);
    setMapping(deriveInitialMapping(p));
    setLinkingMode(job.linking_mode ?? "none");
    setJob(job);
    setReport(EMPTY_REPORT);
  };

  const resetAll = () => {
    setPreview(null);
    setMapping({});
    setLinkingMode("none");
    setJob(null);
    setReport(EMPTY_REPORT);
    setFileInputKey((n) => n + 1);
  };

  const commitSelected = (j: ImportJob) => {
    setJob(j);
    setReport(EMPTY_REPORT);
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">رفع ملفات السجلات</h1>
        <p className="mt-1 text-sm text-slate-500">استيراد CSV أو Excel، ثم ربط الأعمدة والتحقق قبل الحفظ.</p>
      </header>

      {!preview || !job ? (
        <UploadStep key={fileInputKey} onUploaded={startFresh} />
      ) : isActive(job.status) ? (
        <ProgressStep job={job} onJobChange={commitSelected} onReset={resetAll} />
      ) : report.status === "ready" ? (
        <ReviewStep
          job={job}
          report={report}
          onEdit={() => setReport(EMPTY_REPORT)}
          onCommit={commitSelected}
          onReset={resetAll}
        />
      ) : (
        <MappingStep
          preview={preview}
          job={job}
          mapping={mapping}
          linkingMode={linkingMode}
          onMappingChange={setMapping}
          onLinkingChange={setLinkingMode}
          onJobChange={commitSelected}
          onValidate={setReport}
          onReset={resetAll}
        />
      )}

      <JobsSection onResume={startFresh} />
    </div>
  );
}

/* ------------------------------- Step 1 ------------------------------- */

function UploadStep({ onUploaded }: { onUploaded: (job: ImportJob, preview: ImportPreview) => void }) {
  const mutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await api.post("/imports/upload", form);
      return data as { job: ImportJob; preview: ImportPreview };
    },
    onSuccess: (data) => onUploaded(data.job, data.preview),
  });

  const fieldsQuery = useQuery({
    queryKey: ["import-fields"],
    queryFn: async () => {
      const { data } = await api.get<{ max_rows: number }>("/imports/fields");
      return data;
    },
  });
  const maxRows = fieldsQuery.data?.max_rows ?? 500_000;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-base font-bold text-slate-900">الخطوة 1 — اختيار الملف</h2>
      <p className="mt-1 text-sm text-slate-500">ملف CSV بترميز UTF-8 أو XLSX بحد أقصى {maxRows.toLocaleString("ar-EG")} صف.</p>

      <button
        type="button"
        onClick={async () => {
          const { data } = await api.get("/imports/template/csv", { responseType: "blob" });
          downloadBlob(data, "template.csv");
        }}
        className="mt-2 text-sm text-sky-700 underline hover:text-sky-900"
      >
        تنزيل قالب CSV جاهز
      </button>

      {mutation.isError && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(mutation.error)}
        </div>
      )}

      <label className="mt-5 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-12 text-center transition hover:border-slate-400 hover:bg-slate-100">
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) mutation.mutate(file);
          }}
        />
        <span className="text-sm font-medium text-slate-600">
          {mutation.isPending ? "جارٍ الرفع…" : "اضغط لاختيار ملف أو اسحبه هنا"}
        </span>
        <span className="mt-1 text-xs text-slate-400">يجب أن يحوي الملف صف عناوين في السطر الأول</span>
      </label>
    </section>
  );
}

/* ------------------------------- Step 2 ------------------------------- */

function MappingStep({
  preview,
  job,
  mapping,
  linkingMode,
  onMappingChange,
  onLinkingChange,
  onJobChange,
  onValidate,
  onReset,
}: {
  preview: ImportPreview;
  job: ImportJob | null;
  mapping: Record<string, string>;
  linkingMode: string;
  onMappingChange: (m: Record<string, string>) => void;
  onLinkingChange: (m: string) => void;
  onJobChange: (j: ImportJob) => void;
  onValidate: (r: ImportValidationReport) => void;
  onReset: () => void;
}) {
  const queryClient = useQueryClient();
  const [saveOpen, setSaveOpen] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateDescription, setTemplateDescription] = useState("");

  const templatesQuery = useQuery({
    queryKey: ["mapping-templates"],
    queryFn: async () => {
      const { data } = await api.get<{ items: MappingTemplate[] }>("/mapping-templates");
      return data;
    },
  });
  const templates = templatesQuery.data?.items ?? [];

  const saveMapping = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ job: ImportJob }>(`/imports/jobs/${preview.job_id}/mapping`, {
        mapping: toNumber(mapping),
        linking_mode: linkingMode,
      });
      return data.job;
    },
    onSuccess: onJobChange,
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ImportValidationReport>(`/imports/jobs/${preview.job_id}/validate`);
      return data;
    },
    onSuccess: onValidate,
  });

  const saveTemplateMutation = useMutation({
    mutationFn: async () => {
      await api.post("/mapping-templates", {
        name: templateName,
        description: templateDescription || null,
        mapping: toNumber(mapping),
        linking_mode: linkingMode,
      });
    },
    onSuccess: async () => {
      setSaveOpen(false);
      setTemplateName("");
      setTemplateDescription("");
      await queryClient.invalidateQueries({ queryKey: ["mapping-templates"] });
    },
  });

  const fullNameBound = Boolean(mapping.full_name && mapping.full_name !== "");

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">الخطوة 2 — ربط الأعمدة</h2>
          <p className="mt-1 text-sm text-slate-500">
            {preview.filename} · {preview.total_rows.toLocaleString("ar-EG")} صف
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="field-input w-56"
            defaultValue=""
            onChange={(e) => {
              const entry = templates.find((t) => String(t.id) === e.target.value);
              if (!entry) return;
              const next: Record<string, string> = {};
              for (const [field, col] of Object.entries(entry.mapping)) next[field] = String(col);
              onMappingChange(next);
              onLinkingChange(entry.linking_mode);
            }}
          >
            <option value="">قوالب ربط محفوظة…</option>
            {templates.map((t) => (
              <option key={t.id} value={String(t.id)}>
                {t.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => setSaveOpen((v) => !v)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            حفظ كقالب
          </button>
          <button type="button" onClick={onReset} className="text-sm text-slate-500 underline hover:text-slate-800">
            اختيار ملف آخر
          </button>
        </div>
      </div>

      {saveOpen && (
        <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg bg-slate-50 p-3">
          <label className="block flex-1">
            <span className="mb-1 block text-xs font-medium text-slate-600">اسم القالب *</span>
            <input className="field-input" value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder="مثلاً: ملف التقارير الشهرية" />
          </label>
          <label className="block flex-1">
            <span className="mb-1 block text-xs font-medium text-slate-600">وصف</span>
            <input className="field-input" value={templateDescription} onChange={(e) => setTemplateDescription(e.target.value)} />
          </label>
          <button
            type="button"
            disabled={!templateName.trim() || saveTemplateMutation.isPending}
            onClick={() => saveTemplateMutation.mutate()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-40"
          >
            حفظ
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-700">ربط حقول السجل بالأعمدة</h3>
          <div className="space-y-2">
            {(preview.fields ?? []).map((field) => (
              <div key={field.key} className="flex items-center gap-3 text-sm">
                <span className={`w-40 shrink-0 ${field.required ? "font-semibold text-slate-900" : "text-slate-600"}`}>
                  {field.label}
                  {field.required && <span className="text-red-500"> *</span>}
                </span>
                <select
                  className="field-input flex-1"
                  value={mapping[field.key] ?? ""}
                  onChange={(e) => onMappingChange({ ...mapping, [field.key]: e.target.value })}
                >
                  <option value="">— غير مربوط —</option>
                  {preview.headers.map((header, index) => (
                    <option key={index} value={String(index)}>
                      #{index + 1} — {header || "بدون عنوان"}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <div className="mt-5">
            <h3 className="mb-2 text-sm font-semibold text-slate-700">ربط الوالدين (اختياري)</h3>
            <select className="field-input" value={linkingMode} onChange={(e) => onLinkingChange(e.target.value)}>
              {Object.entries(preview.linking_modes ?? {}).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {(saveMapping.isError || validateMutation.isError) && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {errorMessage(saveMapping.error ?? validateMutation.error)}
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={saveMapping.isPending}
              onClick={() => saveMapping.mutate()}
              className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {saveMapping.isPending ? "جارٍ الحفظ…" : "حفظ المطابقة"}
            </button>
            <button
              type="button"
              title={!fullNameBound ? "اربط حقل الاسم الكامل أولاً" : ""}
              disabled={!fullNameBound || job === null || validateMutation.isPending}
              onClick={() => validateMutation.mutate()}
              className="rounded-lg border border-slate-900 bg-white px-5 py-2.5 text-sm font-semibold text-slate-900 hover:bg-slate-50 disabled:opacity-40"
            >
              {validateMutation.isPending ? "جارٍ التحقق…" : "التحقق من الملف"}
            </button>
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200">
          <h3 className="border-b border-slate-200 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-700">
            معاينة أول {preview.rows.length} صف
          </h3>
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-100 text-slate-600">
                <tr>
                  {(preview.headers ?? []).map((header, i) => (
                    <th key={i} className="whitespace-nowrap px-2 py-1.5 font-medium">
                      {header || `عمود ${i + 1}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(preview.rows ?? []).map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j} className="ltr whitespace-nowrap px-2 py-1 text-slate-700">
                        {cell ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ------------------------------- Step 3 ------------------------------- */

function ReviewStep({
  job,
  report,
  onEdit,
  onCommit,
  onReset,
}: {
  job: ImportJob;
  report: ImportValidationReport;
  onEdit: () => void;
  onCommit: (job: ImportJob) => void;
  onReset: () => void;
}) {
  const commitMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ job: ImportJob }>(`/imports/jobs/${job.id}/commit`, {
        skip_invalid: true,
      });
      return data.job;
    },
    onSuccess: onCommit,
  });

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-bold text-slate-900">الخطوة 3 — نتائج التحقق</h2>
        <button type="button" onClick={onReset} className="text-sm text-slate-500 underline hover:text-slate-800">
          اختيار ملف آخر
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="إجمالي الصفوف" value={report.total_rows} tone="text-slate-900" />
        <Stat label="صالح" value={report.valid_rows} tone="text-emerald-700" />
        <Stat label="به أخطاء" value={report.invalid_rows} tone="text-red-600" />
        <Stat label="عدد المحاذير" value={report.warnings_count} tone="text-amber-600" />
      </div>

      {report.errors.length > 0 && (
        <div className="mt-5 overflow-hidden rounded-lg border border-red-200">
          <h3 className="border-b border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">
            الأخطاء{report.errors_truncated ? " (أول 200 فقط)" : ""}
          </h3>
          <div className="max-h-72 overflow-auto">
            <table className="w-full text-xs">
              <thead className="bg-red-50/50 text-red-700">
                <tr>
                  <th className="ltr px-2 py-1.5 text-start">الصف</th>
                  <th className="px-2 py-1.5 text-start">الحقل</th>
                  <th className="px-2 py-1.5 text-start">الرسالة</th>
                  <th className="px-2 py-1.5 text-start">القيمة</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-red-100">
                {report.errors.map((error, i) => (
                  <ErrorRow key={i} error={error} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {commitMutation.isError && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(commitMutation.error)}
        </div>
      )}

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          disabled={!report.can_commit || commitMutation.isPending}
          onClick={() => commitMutation.mutate()}
          className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-40"
        >
          {commitMutation.isPending ? "البدء…" : "بدء الاستيراد"}
        </button>
        <button
          type="button"
          onClick={onEdit}
          className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          تعديل المطابقة
        </button>
      </div>
    </section>
  );
}

function ErrorRow({ error }: { error: ImportError }) {
  return (
    <tr>
      <td className="ltr px-2 py-1.5 text-red-700">{error.row}</td>
      <td className="px-2 py-1.5 text-red-700">{error.field}</td>
      <td className="px-2 py-1.5 text-slate-700">{error.message}</td>
      <td className="ltr px-2 py-1.5 text-slate-500">{error.value ?? ""}</td>
    </tr>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-4 text-center">
      <div className={`text-2xl font-bold ${tone}`}>{value.toLocaleString("ar-EG")}</div>
      <div className="mt-1 text-xs text-slate-500">{label}</div>
    </div>
  );
}

/* --------------------------- progress / commit ------------------------- */

function ProgressStep({
  job,
  onJobChange,
  onReset,
}: {
  job: ImportJob;
  onJobChange: (j: ImportJob) => void;
  onReset: () => void;
}) {
  const cancelMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ job: ImportJob }>(`/imports/jobs/${job.id}/cancel`);
      return data.job;
    },
    onSuccess: onJobChange,
  });

  useEffect(() => {
    if (!isActive(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const { data } = await api.get<{ job: ImportJob }>(`/imports/jobs/${job.id}`);
        onJobChange(data.job);
      } catch {
        // transient failure; the next tick retries
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job.id, job.status, onJobChange]);

  const done = ["completed", "failed", "cancelled"].includes(job.status);
  const percent = job.progress ?? 0;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-slate-900">
            {done ? STATUS_LABELS[job.status] ?? job.status : "جارٍ الاستيراد…"}
          </h2>
          <p className="ltr mt-1 text-sm text-slate-500">{job.filename}</p>
        </div>
        {!done && (
          <button
            type="button"
            disabled={cancelMutation.isPending}
            onClick={() => {
              if (window.confirm("إلغاء الاستيراد؟ تبقى الصفوف الملتزمة حتى الآن.")) cancelMutation.mutate();
            }}
            className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            إلغاء الاستيراد
          </button>
        )}
        {done && (
          <button type="button" onClick={onReset} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700">
            استيراد ملف آخر
          </button>
        )}
      </div>

      {done && job.message && (
        <div className="mb-4 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-700">{job.message}</div>
      )}
      {cancelMutation.isError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(cancelMutation.error)}
        </div>
      )}

      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-slate-600">
          {(job.processed_rows ?? 0).toLocaleString("ar-EG")} / {(job.total_rows ?? 0).toLocaleString("ar-EG")} صف
        </span>
        <span className="ltr font-semibold text-slate-800">{percent}%</span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-slate-900 transition-all duration-500"
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="تمت المعالجة" value={job.processed_rows ?? 0} tone="text-slate-900" />
        <Stat label="أُنشئ" value={job.created_rows ?? 0} tone="text-emerald-700" />
        <Stat label="حُدّث" value={job.updated_rows ?? 0} tone="text-sky-700" />
        <Stat label="فشل" value={job.failed_rows ?? 0} tone="text-red-600" />
      </div>

      {done && (job.error_report?.length ?? 0) > 0 && (
        <div className="mt-5 overflow-hidden rounded-lg border border-red-200">
          <h3 className="border-b border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">تقرير الأخطاء</h3>
          <div className="max-h-64 overflow-auto">
            <table className="w-full text-xs">
              <thead className="bg-red-50/50 text-red-700">
                <tr>
                  <th className="ltr px-2 py-1.5 text-start">الصف</th>
                  <th className="px-2 py-1.5 text-start">الرسالة</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-red-100">
                {(job.error_report ?? []).slice(0, 200).map((error, i) => (
                  <tr key={i}>
                    <td className="ltr px-2 py-1.5 text-red-700">{error.row}</td>
                    <td className="px-2 py-1.5 text-slate-700">{error.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

/* --------------------------- recent jobs list -------------------------- */

function JobsSection({ onResume }: { onResume: (job: ImportJob, preview: ImportPreview) => void }) {
  const queryClient = useQueryClient();
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);

  const jobsQuery = useQuery({
    queryKey: ["import-jobs"],
    queryFn: async () => {
      const { data } = await api.get<Page<ImportJob>>("/imports/jobs?limit=50");
      return data;
    },
    refetchInterval: 5000,
  });

  const detailQuery = useQuery({
    queryKey: ["import-job-detail", selectedJobId],
    queryFn: async () => {
      const { data } = await api.get<{ job: ImportJob }>(`/imports/jobs/${selectedJobId}`);
      return data.job;
    },
    enabled: selectedJobId !== null,
    refetchInterval: 3000,
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => api.delete(`/imports/jobs/${id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["import-jobs"] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: async (job: ImportJob) => {
      const { data } = await api.get<{ job: ImportJob; preview: ImportPreview }>(`/imports/jobs/${job.id}/preview`);
      return data;
    },
    onSuccess: (data) => onResume(data.job, data.preview),
  });

  const detail = detailQuery.data;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="mb-4 text-base font-bold text-slate-900">عمليات الاستيراد السابقة</h2>

      {detail && (
        <div className="mb-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold text-slate-800">
              {detail.filename} <StatusBadge status={detail.status} />
            </span>
            <button type="button" onClick={() => setSelectedJobId(null)} className="text-sm text-slate-500 underline hover:text-slate-800">
              إغلاق
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="تمت المعالجة" value={detail.processed_rows ?? 0} tone="text-slate-900" />
            <Stat label="أُنشئ" value={detail.created_rows ?? 0} tone="text-emerald-700" />
            <Stat label="حُدّث" value={detail.updated_rows ?? 0} tone="text-sky-700" />
            <Stat label="فشل" value={detail.failed_rows ?? 0} tone="text-red-600" />
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 text-start font-semibold">الملف</th>
              <th className="ltr px-3 py-2 text-start font-semibold">الصفوف</th>
              <th className="px-3 py-2 text-start font-semibold">الحالة</th>
              <th className="ltr px-3 py-2 text-start font-semibold">التقدم</th>
              <th className="ltr px-3 py-2 text-start font-semibold">التاريخ</th>
              <th className="px-3 py-2 text-end font-semibold">إجراءات</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(jobsQuery.data?.items ?? []).map((job) => {
              const deletable = !["pending", "validating", "processing"].includes(job.status);
              return (
                <tr key={job.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-800">{job.filename}</td>
                  <td className="ltr px-3 py-2 text-slate-600">{job.total_rows ?? 0}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="ltr px-3 py-2 text-slate-600">{job.progress ?? 0}%</td>
                  <td className="ltr px-3 py-2 text-slate-500">{formatDate(job.created_at)}</td>
                  <td className="px-3 py-2 text-end">
                    <button type="button" onClick={() => setSelectedJobId(job.id)} className="text-sm text-sky-700 underline hover:text-sky-900">
                      عرض
                    </button>
                    {deletable && (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm("استئناف هذا الملف في المعالج؟")) resumeMutation.mutate(job);
                          }}
                          className="ms-3 text-sm text-emerald-700 underline hover:text-emerald-900"
                        >
                          استئناف
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm(`حذف مهمة الاستيراد "${job.filename}"؟`)) {
                              deleteMutation.mutate(job.id);
                            }
                          }}
                          className="ms-3 text-sm text-red-600 underline hover:text-red-700"
                        >
                          حذف
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              );
            })}
            {jobsQuery.data?.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-400">لا توجد عمليات استيراد</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tones: Record<string, string> = {
    pending: "border-slate-200 bg-slate-100 text-slate-600",
    validating: "border-sky-200 bg-sky-50 text-sky-700",
    ready: "border-emerald-200 bg-emerald-50 text-emerald-700",
    processing: "border-amber-200 bg-amber-50 text-amber-700",
    completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
    failed: "border-red-200 bg-red-50 text-red-600",
    cancelled: "border-slate-300 bg-slate-100 text-slate-500",
  };
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs ${tones[status] ?? "border-slate-200 bg-slate-50 text-slate-600"}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

function downloadBlob(data: Blob, filename: string): void {
  const url = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "short" });
}