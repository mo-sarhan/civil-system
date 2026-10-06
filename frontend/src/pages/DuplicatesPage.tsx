import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/context";
import { api, errorMessage } from "../lib/api";
import type { CompareResult, DuplicatePerson, DuplicatesResult } from "../lib/types";

const THRESHOLDS = [0.6, 0.7, 0.8];

const FIELD_LABELS: Record<string, string> = {
  national_id: "رقم القومى",
  full_name: "الاسم الكامل",
  first_name: "الاسم الأول",
  father_name: "اسم الأب",
  grandfather_name: "اسم الجد",
  family_name: "اللقب",
  gender: "النوع",
  birth_date: "تاريخ الميلاد",
  death_date: "تاريخ الوفاة",
  birth_place: "محل الميلاد",
  father_id: "الأب",
  mother_id: "الأم",
  notes: "ملاحظات",
};

export default function DuplicatesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === "admin";
  const [threshold, setThreshold] = useState(0.6);
  const [limit, setLimit] = useState(50);
  const [pair, setPair] = useState<[number, number] | null>(null);

  const scan = useQuery({
    queryKey: ["duplicates", threshold, limit],
    queryFn: async () => {
      const { data } = await api.get<DuplicatesResult>(
        `/duplicates?threshold=${threshold}&limit=${limit}`,
      );
      return data;
    },
    enabled: isAdmin,
    staleTime: 15_000,
  });

  const compare = useQuery({
    queryKey: ["duplicates", "compare", pair?.[0], pair?.[1]],
    queryFn: async () => {
      const { data } = await api.get<CompareResult>(
        `/duplicates/compare?a=${pair![0]}&b=${pair![1]}`,
      );
      return data;
    },
    enabled: Boolean(pair),
  });

  const mergeMutation = useMutation({
    mutationFn: async ({ targetId, sourceId }: { targetId: number; sourceId: number }) => {
      const { data } = await api.post("/duplicates/merge", { target_id: targetId, source_id: sourceId });
      return data as { message: string; stats: Record<string, number> };
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["duplicates"] }),
        queryClient.invalidateQueries({ queryKey: ["persons"] }),
        queryClient.invalidateQueries({ queryKey: ["stats"] }),
      ]);
      setPair(null);
    },
  });

  if (!isAdmin) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white px-6 py-10 text-center text-sm text-slate-500">
        استعراض المكررات ودمجها متاح للمدير فقط.
      </div>
    );
  }

  const groups = scan.data?.groups ?? [];
  const pairMembers = (): [DuplicatePerson, DuplicatePerson] | null => {
    if (!pair) return null;
    const all: DuplicatePerson[] = [];
    for (const g of groups) all.push(...(g.persons ?? []));
    const a = all.find((m) => m.id === pair[0]);
    const b = all.find((m) => m.id === pair[1]);
    return a && b ? [a, b] : null;
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">المكررات</h1>
          <p className="mt-1 text-sm text-slate-500">
            {scan.data
              ? `${scan.data.total_groups.toLocaleString("ar-EG")} مجموعة مشتبه بها`
              : " "}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm text-slate-600">
            الحد الأدنى للتشابه
            <select
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="field-input ms-2 w-24"
            >
              {THRESHOLDS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm text-slate-600">
            الحد الأقصى
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="field-input ms-2 w-24"
            >
              {[50, 100, 200].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={scan.isPending}
            onClick={() => scan.refetch()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {scan.isPending ? "جارٍ الفحص…" : "إعادة الفحص"}
          </button>
        </div>
      </header>

      {scan.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(scan.error)}
        </div>
      )}
      {scan.data && groups.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
          لا توجد مجموعات مكررة بهذا الحد الأدنى.
        </div>
      )}

      {mergeMutation.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(mergeMutation.error)}
        </div>
      )}
      {mergeMutation.isSuccess && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          تم الدمج ({JSON.stringify(mergeMutation.data.message)})
          <span className="ms-2 text-xs">أُعيدت توجيه {mergeMutation.data.stats?.references ?? 0} إشارة</span>
        </div>
      )}

      {groups.map((group) => {
        const members = group.persons ?? [];
        const ids = members.map((m) => m.id);
        return (
          <section key={group.key} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-semibold text-slate-800">{group.reason}</div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span>{ids.length} سجل</span>
                <span className="ltr">ثقة {Math.round(group.confidence * 100)}%</span>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {members.map((m) => (
                <MemberPill
                  key={m.id}
                  member={m}
                  selected={pair?.includes(m.id) ?? false}
                  onToggle={() =>
                    setPair((prev) => {
                      const current: number[] = prev ?? [];
                      if (current.includes(m.id)) {
                        const rest = current.filter((x) => x !== m.id);
                        return rest.length === 2 ? [rest[0], rest[1]] : null;
                      }
                      const next = [...current, m.id];
                      return next.length >= 2
                        ? [next[next.length - 2], next[next.length - 1]]
                        : null;
                    })
                  }
                />
              ))}
            </div>
          </section>
        );
      })}

      {pair && (
        <ComparePanel
          key={`${pair[0]}-${pair[1]}`}
          pair={pairMembers()}
          loading={compare.isPending}
          error={errorMessage(compare.error ?? null)}
          data={compare.data}
          onMerge={(targetId, sourceId) => {
            if (window.confirm("تأكيد دمج السجلين؟ لا يمكن التراجع عن هذه العملية.")) {
              mergeMutation.mutate({ targetId, sourceId });
            }
          }}
          onClose={() => setPair(null)}
        />
      )}
    </div>
  );
}

function MemberPill({
  member,
  selected,
  onToggle,
}: {
  member: DuplicatePerson;
  selected: boolean;
  onToggle: () => void;
}) {
  const label = `${member.full_name}${member.birth_date ? ` (${member.birth_date})` : ""}`;
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`rounded-lg border px-3 py-2 text-sm transition ${
        selected
          ? "border-slate-900 bg-slate-900 text-white"
          : "border-slate-200 bg-slate-50 text-slate-800 hover:border-slate-300"
      }`}
    >
      <span className="font-medium">{label}</span>
      <span className={`ms-2 text-xs ${selected ? "text-slate-300" : "text-slate-400"}`}>
        #{member.id} · {member.children ?? 0} أبناء · {member.spouses ?? 0} زيجات
      </span>
    </button>
  );
}

function ComparePanel({
  pair,
  loading,
  error,
  data,
  onMerge,
  onClose,
}: {
  pair: [DuplicatePerson, DuplicatePerson] | null;
  loading: boolean;
  error: string;
  data: CompareResult | undefined;
  onMerge: (targetId: number, sourceId: number) => void;
  onClose: () => void;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-bold text-slate-900">مقارنة السجلين</h2>
        <button type="button" onClick={onClose} className="text-sm text-slate-500 underline hover:text-slate-800">
          إغلاق
        </button>
      </div>
      {loading && <div className="py-6 text-center text-sm text-slate-400">جارٍ المقارنة…</div>}
      {!loading && error && <div className="text-sm text-red-600">{error}</div>}
      {!loading && data && (
        <>
          <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <PersonMini id={data.a.id} name={data.a.full_name} data={data.a} highlight="مصدر محتمل" />
            <PersonMini id={data.b.id} name={data.b.full_name} data={data.b} highlight="مصدر محتمل" />
          </div>

          <div className="overflow-hidden rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-3 py-2 text-start font-semibold">الحقل</th>
                  <th className="ltr px-3 py-2 text-start font-semibold">السجل {data.a.id}</th>
                  <th className="ltr px-3 py-2 text-start font-semibold">السجل {data.b.id}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.fields.map((field) => (
                  <tr key={field.field} className={field.same ? "" : "bg-amber-50/60"}>
                    <td className="px-3 py-2 text-slate-700">
                      {FIELD_LABELS[field.field] ?? field.field}
                      {!field.same && <span className="ms-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">مختلف</span>}
                    </td>
                    <td className="ltr px-3 py-2 text-slate-800">{formatCell(field.a)}</td>
                    <td className="ltr px-3 py-2 text-slate-800">{formatCell(field.b)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-600">
              تشابه الاسم:{" "}
              <span dir="ltr" className="font-semibold">
                {Math.round(data.name_similarity * 100)}%
              </span>{" "}
              · التوصية: <span className="font-semibold">{data.recommendation}</span>
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => onMerge(data.a.id, data.b.id)}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
              >
                إبقاء #{data.a.id} ودمج #{data.b.id}
              </button>
              <button
                type="button"
                onClick={() => onMerge(data.b.id, data.a.id)}
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                إبقاء #{data.b.id} ودمج #{data.a.id}
              </button>
            </div>
          </div>
        </>
      )}
      {!loading && !data && !error && pair && (
        <div className="py-6 text-center text-sm text-slate-400">اختر السجلين للمقارنة</div>
      )}
    </div>
  );
}

function PersonMini({ id, name, data }: { id: number; name: string; data: DuplicatePerson; highlight: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-center justify-between">
        <Link to={`/persons/${id}`} className="font-semibold text-slate-900 hover:underline">
          {name}
        </Link>
        <span className="ltr text-xs text-slate-400">#{id}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
        <span className="ltr">{data.national_id ?? "—"}</span>
        {data.birth_date && <span className="ltr">· {data.birth_date}</span>}
        <span>· {data.children ?? 0} أبناء</span>
        <span>· {data.spouses ?? 0} زيجات</span>
      </div>
    </div>
  );
}

function formatCell(value: string | number | null): string {
  return value === null || value === "" ? "—" : String(value);
}