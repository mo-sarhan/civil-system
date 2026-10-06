import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../lib/api";

interface Overview {
  total_persons: number;
  active_persons: number;
  merged_persons: number;
  by_gender: { M: number; F: number; unknown: number };
  alive: number;
  deceased: number;
  with_national_id: number;
  without_national_id: number;
  with_birth_date: number;
  missing_father: number;
  missing_mother: number;
  marriages: number;
  active_marriages: number;
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-bold text-slate-900">
        {value.toLocaleString("ar-EG")}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["stats", "overview"],
    queryFn: async () => {
      const { data } = await api.get<Overview>("/stats");
      return data;
    },
    refetchInterval: 60_000,
  });

  if (isError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {errorMessage(error)}
      </div>
    );
  }

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">لوحة المعلومات</h1>
        <p className="mt-1 text-sm text-slate-500">
          {isPending ? "جارٍ التحميل…" : "ملخص لحالة السجل"}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="إجمالي الأشخاص" value={data?.total_persons ?? 0} />
        <Stat label="الذكور" value={data?.by_gender.M ?? 0} />
        <Stat label="الإناث" value={data?.by_gender.F ?? 0} />
        <Stat label="الزيجات" value={data?.marriages ?? 0} hint={`${data?.active_marriages ?? 0} سارية`} />
        <Stat label="على قيد الحياة" value={data?.alive ?? 0} />
        <Stat label="الوفيات" value={data?.deceased ?? 0} />
        <Stat
          label="بدون أب مسجل"
          value={data?.missing_father ?? 0}
          hint="سجلات تنقصها صلة"
        />
        <Stat label="بدون رقم قومى" value={data?.without_national_id ?? 0} />
      </div>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          to="/persons"
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
        >
          تصفح الأشخاص
        </Link>
        <Link
          to="/tree"
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          شجرة العائلة
        </Link>
        <Link
          to="/imports"
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          رفع ملف
        </Link>
      </div>
    </div>
  );
}
