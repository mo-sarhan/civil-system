import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../lib/api";
import type { Page, Person } from "../lib/types";

interface Filters {
  q: string;
  gender: "" | "M" | "F";
  page: number;
}

const EMPTY: Filters = { q: "", gender: "", page: 1 };

/** Debounced copy of the search box so typing does not fire a request per key. */
function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function PersonsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const debouncedQuery = useDebounced(filters.q);

  const params = new URLSearchParams();
  params.set("page", String(filters.page));
  params.set("page_size", "25");
  if (debouncedQuery) params.set("q", debouncedQuery);
  if (filters.gender) params.set("gender", filters.gender);

  const { data, isPending, isError, error } = useQuery({
    queryKey: ["persons", params.toString()],
    queryFn: async () => {
      const { data } = await api.get<Page<Person>>(`/persons?${params.toString()}`);
      return data;
    },
    placeholderData: (previous) => previous,
  });

  return (
    <div>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">الأشخاص</h1>
          <p className="mt-1 text-sm text-slate-500">
            {data ? `${data.total.toLocaleString("ar-EG")} سجل` : " "}
          </p>
        </div>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          type="search"
          placeholder="بحث بالاسم أو رقم القومى…"
          value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value, page: 1 })}
          className="field-input max-w-xs"
        />
        <select
          value={filters.gender}
          onChange={(e) =>
            setFilters({ ...filters, gender: e.target.value as Filters["gender"], page: 1 })
          }
          className="field-input w-40"
        >
          <option value="">النوع: الكل</option>
          <option value="M">ذكر</option>
          <option value="F">أنثى</option>
        </select>
        {(debouncedQuery || filters.gender) && (
          <button
            type="button"
            onClick={() => setFilters(EMPTY)}
            className="text-sm text-slate-500 underline hover:text-slate-800"
          >
            مسح الفلاتر
          </button>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 text-start font-semibold">الاسم</th>
              <th className="px-4 py-3 text-start font-semibold">رقم القومى</th>
              <th className="px-4 py-3 text-start font-semibold">النوع</th>
              <th className="px-4 py-3 text-start font-semibold">تاريخ الميلاد</th>
              <th className="px-4 py-3 text-start font-semibold">الوالد</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isPending && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-500">
                  جارٍ التحميل…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-red-600">
                  {errorMessage(error)}
                </td>
              </tr>
            )}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-500">
                  لا توجد نتائج مطابقة
                </td>
              </tr>
            )}
            {data?.items.map((person) => (
              <tr key={person.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    to={`/persons/${person.id}`}
                    className="font-medium text-slate-900 hover:underline"
                  >
                    {person.full_name}
                  </Link>
                </td>
                <td className="ltr px-4 py-3 text-slate-600">
                  {person.national_id ?? "—"}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {person.gender === "M" ? "ذكر" : person.gender === "F" ? "أنثى" : "—"}
                </td>
                <td className="ltr px-4 py-3 text-slate-600">
                  {person.birth_date ?? "—"}
                </td>
                <td className="px-4 py-3 text-slate-600">{person.father_id ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.pages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
          <button
            type="button"
            disabled={data.page <= 1}
            onClick={() => setFilters({ ...filters, page: filters.page - 1 })}
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
            onClick={() => setFilters({ ...filters, page: filters.page + 1 })}
            className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 disabled:opacity-40"
          >
            التالي
          </button>
        </div>
      )}
    </div>
  );
}
