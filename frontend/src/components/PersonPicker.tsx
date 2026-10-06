import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Page, Person } from "../lib/types";

interface Props {
  label: string;
  value: number | null;
  onChange: (person: Person | null) => void;
  /** Placeholder shown before the user types. */
  placeholder?: string;
}

/**
 * Name search backed by `GET /persons`. Used wherever a form needs to point at
 * another record (father, mother) without forcing the user to know an ID.
 */
export default function PersonPicker({ label, value, onChange, placeholder }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<Person | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  const params = new URLSearchParams({ page: "1", page_size: "8" });
  if (query.trim()) params.set("q", query.trim());

  const { data, isFetching } = useQuery({
    queryKey: ["persons", "picker", query, value],
    queryFn: async () => {
      const { data } = await api.get<Page<Person>>(`/persons?${params.toString()}`);
      return data;
    },
    enabled: open,
    staleTime: 10_000,
  });

  // Load the current value's label so the control is not blank on first paint.
  useEffect(() => {
    if (!value || selected?.id === value) return;
    let cancelled = false;
    void api
      .get<Person>(`/persons/${value}`)
      .then((res) => {
        if (!cancelled) setSelected(res.data);
      })
      .catch(() => {
        if (!cancelled) setSelected(null);
      });
    return () => {
      cancelled = true;
    };
  }, [value, selected?.id]);

  useEffect(() => {
    if (!open) return;
    function onOutside(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [open]);

  const chosen = value ? selected : null;

  return (
    <div className="relative" ref={boxRef}>
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      <input
        className="field-input"
        placeholder={chosen ? chosen.full_name : (placeholder ?? "اكتب الاسم للبحث…")}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
      />
      {open && (
        <div className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
          {isFetching && (
            <div className="px-3 py-2 text-sm text-slate-400">جارٍ البحث…</div>
          )}
          {data?.items.length === 0 && !isFetching && (
            <div className="px-3 py-2 text-sm text-slate-400">لا توجد نتائج</div>
          )}
          {data?.items.map((person) => (
            <button
              key={person.id}
              type="button"
              className="block w-full px-3 py-2 text-start text-sm hover:bg-slate-50"
              onClick={() => {
                setSelected(person);
                onChange(person);
                setQuery("");
                setOpen(false);
              }}
            >
              <span className="font-medium text-slate-800">{person.full_name}</span>
              <span className="ltr me-2 text-xs text-slate-400">
                {person.national_id ? ` · ${person.national_id}` : ""}
              </span>
              {person.birth_date && (
                <span className="ltr text-xs text-slate-400"> · {person.birth_date}</span>
              )}
            </button>
          ))}
        </div>
      )}
      {value && (
        <button
          type="button"
          className="mt-1 text-xs text-slate-500 underline hover:text-slate-800"
          onClick={() => {
            setSelected(null);
            onChange(null);
            setQuery("");
          }}
        >
          إزالة
        </button>
      )}
    </div>
  );
}
