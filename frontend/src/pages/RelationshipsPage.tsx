import { useQuery } from "@tanstack/react-query";
import { Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../lib/api";
import type { Person, RelationshipResult } from "../lib/types";
import PersonPicker from "../components/PersonPicker";

export default function RelationshipsPage() {
  const navigate = useNavigate();

  const [from, setFrom] = useState<Person | null>(null);
  const [to, setTo] = useState<Person | null>(null);
  const [searched, setSearched] = useState(false);

  const fromId = from?.id ?? null;
  const toId = to?.id ?? null;

  const query = useQuery({
    queryKey: ["relationship", fromId, toId],
    queryFn: async () => {
      const { data } = await api.get<RelationshipResult>(
        `/relationship?a=${fromId}&b=${toId}`,
      );
      return data;
    },
    enabled: searched && fromId !== null && toId !== null && fromId !== toId,
    staleTime: 30_000,
  });

  const swap = () => {
    setFrom(to);
    setTo(from);
  };

  const clear = () => {
    setSearched(false);
  };

  const openOnTree = (result: RelationshipResult) => {
    const path = result.path.map((s) => s.person_id).join(",");
    navigate(
      `/tree?person_id=${result.a}&path=${path}&rel=${encodeURIComponent(
        result.relation ?? "",
      )}&deg=${result.distance}`,
    );
  };

  const ready = fromId !== null && toId !== null && fromId !== toId;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">صلة القرابة</h1>
        <p className="mt-1 text-sm text-slate-500">
          ابحث عن صلة القرابة بين شخصين، وأبرز المسار الحقيقي على الشجرة
        </p>
      </header>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-72">
            <PersonPicker
              label="الشخص الأول"
              value={fromId}
              placeholder="ابحث عن الاسم للاختيار…"
              onChange={(p) => {
                setFrom(p);
                clear();
              }}
            />
          </div>
          <button
            type="button"
            onClick={swap}
            disabled={!from && !to}
            className="mb-0.5 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-40"
            title="تبديل"
            aria-label="تبديل بين الشخصين"
          >
            ⇄
          </button>
          <div className="w-72">
            <PersonPicker
              label="الشخص الثاني"
              value={toId}
              placeholder="ابحث عن الاسم للاختيار…"
              onChange={(p) => {
                setTo(p);
                clear();
              }}
            />
          </div>
          <button
            type="button"
            disabled={!ready || query.isFetching}
            onClick={() => setSearched(true)}
            className="mb-0.5 rounded-lg bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {query.isFetching ? "جارٍ البحث…" : "ابحث عن صلة القرابة"}
          </button>
        </div>
        {ready && from && to && (
          <p className="mt-3 text-sm text-slate-500" dir="rtl">
            {from.full_name} مقابل {to.full_name}
          </p>
        )}
        {!ready && fromId !== null && toId !== null && (
          <p className="mt-3 text-sm text-amber-700" dir="rtl">
            اختر شخصين مختلفين للبحث.
          </p>
        )}
      </div>

      {searched && query.isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {errorMessage(query.error)}
        </div>
      )}

      {searched && query.data && (
        <ResultCard
          result={query.data}
          onOpenTree={() => openOnTree(query.data!)}
        />
      )}
    </div>
  );
}

function ResultCard({
  result,
  onOpenTree,
}: {
  result: RelationshipResult;
  onOpenTree: () => void;
}) {
  const noRelation = !result.relation;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm" dir="rtl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-medium text-slate-400">العلاقة</div>
          <div className="mt-1 text-3xl font-bold text-slate-900">
            {noRelation ? "لا توجد صلة قرابة معروفة" : result.relation}
          </div>
          {result.explanation && (
            <p className="mt-2 text-sm text-slate-600">{result.explanation}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!noRelation && (
            <span className="rounded-lg bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
              درجة القرابة: {result.distance}
            </span>
          )}
          {result.generations !== null && result.generations !== 0 && (
            <span className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
              فرق الأجيال: {result.generations > 0 ? `+` : `−`}{" "}
              {Math.abs(result.generations)}
            </span>
          )}
          {noRelation && (
            <span className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-500">
              قد تكون العلاقة عبر زواج غير مسجَّل أو سجلات ناقصة
            </span>
          )}
        </div>
      </div>

      {result.path.length > 0 && (
        <div className="mt-5">
          <div className="mb-2 text-xs font-medium text-slate-400">
            سلسلة القرابة (كل رابطة = صلة أب/أم أو زواج):
          </div>
          <div className="flex flex-wrap items-center gap-y-2">
            {result.path.map((step, i) => {
              const isFirst = i === 0;
              const isLast = i === result.path.length - 1;
              const ring = isFirst
                ? "ring-emerald-500"
                : isLast
                  ? "ring-red-500"
                  : "ring-slate-300";
              const label = isFirst
                ? "الشخص الأول"
                : isLast
                  ? "الشخص الثاني"
                  : step.role;
              return (
                <Fragment key={step.person_id}>
                  {i > 0 && (
                    <div className="mx-1 flex flex-col items-center" dir="ltr">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                        {result.path[i - 1].relation_to_next}
                      </span>
                      <span className="text-slate-400">←</span>
                    </div>
                  )}
                  <div
                    className={
                      "min-w-[9rem] rounded-xl bg-slate-50 px-3 py-2.5 ring-1 " + ring
                    }
                  >
                    <div className="text-sm font-semibold text-slate-900">
                      {step.full_name}
                    </div>
                    <div className="mt-0.5 text-[11px] text-slate-500">
                      {label}
                      {step.gender === "F" ? " · أنثى" : " · ذكر"}
                    </div>
                  </div>
                </Fragment>
              );
            })}
          </div>
        </div>
      )}

      {!noRelation && (
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={onOpenTree}
            className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            إظهار المسار على الشجرة
          </button>
        </div>
      )}
    </div>
  );
}