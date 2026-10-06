import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/context";
import { api, errorMessage } from "../lib/api";
import type {
  ChildrenResponse,
  FamilySummary,
  ParentsResponse,
  Person,
  RelativesResponse,
  SiblingsResponse,
  SpousesResponse,
} from "../lib/types";
import PersonForm from "../components/PersonForm";

interface PersonBundle extends Person {
  summary: FamilySummary;
  parents: ParentsResponse;
  children: ChildrenResponse;
  siblings: SiblingsResponse;
  spouses: SpousesResponse;
}

export default function PersonDetailPage() {
  const { personId } = useParams();
  const id = Number(personId);
  const navigate = useNavigate();
  const { user } = useAuth();
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const canWrite = user?.role === "editor" || user?.role === "admin";
  const isAdmin = user?.role === "admin";

  const bundle = useQuery({
    queryKey: ["person", id],
    queryFn: async (): Promise<PersonBundle> => {
      const [person, summary, parents, children, siblings, spouses] = await Promise.all([
        api.get<Person>(`/persons/${id}`),
        api.get<FamilySummary>(`/persons/${id}/family-summary`),
        api.get<ParentsResponse>(`/persons/${id}/parents`),
        api.get<ChildrenResponse>(`/persons/${id}/children`),
        api.get<SiblingsResponse>(`/persons/${id}/siblings`),
        api.get<SpousesResponse>(`/persons/${id}/spouses`),
      ]);
      return {
        ...person.data,
        summary: summary.data,
        parents: parents.data,
        children: children.data,
        siblings: siblings.data,
        spouses: spouses.data,
      };
    },
  });

  const relatives = useQuery({
    queryKey: ["person", id, "relatives"],
    queryFn: async () => {
      const { data } = await api.get<RelativesResponse>(`/persons/${id}/relatives`);
      return data;
    },
    staleTime: 60_000,
  });

  const removeMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/persons/${id}`);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["persons"] });
      await queryClient.invalidateQueries({ queryKey: ["stats", "overview"] });
      navigate("/persons");
    },
  });

  const person = bundle.data;

  if (bundle.isError) {
    return <div className="text-red-600">{errorMessage(bundle.error)}</div>;
  }
  if (!person) {
    return <div className="text-slate-500">جارٍ التحميل…</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/persons" className="text-sm text-slate-500 hover:text-slate-800">
            ← العودة إلى الأشخاص
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">{person.full_name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>{genderLabel(person.gender)}</span>
            <span aria-hidden>·</span>
            <span className="ltr">{person.birth_date ?? "تاريخ ميلاد غير معروف"}</span>
            {person.death_date && (
              <>
                <span aria-hidden>·</span>
                <span className="text-slate-400">توفي {person.death_date}</span>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`/persons/${id}/tree`}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
          >
            شجرة العائلة
          </Link>
          {canWrite && !editing && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              تعديل
            </button>
          )}
          {isAdmin && (
            <button
              type="button"
              onClick={() => {
                if (window.confirm(`حذف «${person.full_name}» نهائياً؟`)) removeMutation.mutate();
              }}
              className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50"
            >
              حذف
            </button>
          )}
        </div>
      </div>

      {removeMutation.isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {errorMessage(removeMutation.error)}
        </div>
      )}

      {editing ? (
        <PersonForm
          person={person}
          onCancel={() => setEditing(false)}
          onSaved={async (updated) => {
            await queryClient.setQueryData(["person", id], (old: PersonBundle) => ({
              ...old,
              ...updated,
            }));
            queryClient.invalidateQueries({ queryKey: ["person"] });
            setEditing(false);
          }}
        />
      ) : (
        <>
          <SummaryChips summary={person.summary} />

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Section title="الوالدان">
              {person.parents.father || person.parents.mother ? (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {person.parents.father && (
                    <PersonChip
                      id={person.parents.father.id}
                      name={person.parents.father.full_name}
                      subtitle="الأب"
                    />
                  )}
                  {person.parents.mother && (
                    <PersonChip
                      id={person.parents.mother.id}
                      name={person.parents.mother.full_name}
                      subtitle="الأم"
                    />
                  )}
                </div>
              ) : (
                <Empty text="لا توجد صلات أبوة مسجلة" />
              )}
            </Section>

            <Section title={`الأبناء (${person.children.total})`}>
              {[...person.children.as_father, ...person.children.as_mother].length ? (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {[...person.children.as_father, ...person.children.as_mother].map((child) => (
                    <PersonChip key={child.id} id={child.id} name={child.full_name} />
                  ))}
                </div>
              ) : (
                <Empty text="لا يوجد أبناء مسجلون" />
              )}
            </Section>

            <Section title={`الإخوة (${person.siblings.total})`}>
              <RelativeGroups
                groups={[
                  ["أشقاء", person.siblings.full],
                  ["إخوة من الأب", person.siblings.half_paternal],
                  ["إخوة من الأم", person.siblings.half_maternal],
                ]}
              />
            </Section>

            <Section title={`الأزواج (${person.spouses.total})`}>
              {person.spouses.spouses.length ? (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {person.spouses.spouses.map((spouse) => (
                    <PersonChip
                      key={spouse.id}
                      id={spouse.id}
                      name={spouse.full_name}
                      subtitle={spouse.marriage_status ? labelMarriage(spouse.marriage_status) : undefined}
                    />
                  ))}
                </div>
              ) : (
                <Empty text="لا توجد زيجات مسجلة" />
              )}
            </Section>
          </div>

          <Section title="الأقارب" loading={relatives.isPending}>
            {relatives.data && (
              <RelativeGroups
                groups={[
                  ["أعمام وأخوال", relatives.data.uncles_aunts],
                  ["أبناء العم", relatives.data.cousins],
                  ["أبناء الإخوة", relatives.data.nephews_nieces],
                  ["أعمام الوالدين", relatives.data.grand_uncles],
                  ["أخوال الوالدين", relatives.data.grand_aunts],
                  ["أصهار", relatives.data.in_laws],
                ]}
              />
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function SummaryChips({ summary }: { summary: FamilySummary }) {
  const chips = [
    ["الأطفال", summary.children],
    ["الإخوة", summary.siblings],
    ["الأزواج", summary.spouses],
    ["الأجداد", summary.ancestors],
    ["الأحفاد", summary.descendants],
    ["الزيجات", summary.marriages],
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {chips.map(([label, count]) => (
        <div key={label} className="rounded-xl border border-slate-200 bg-white p-4 text-center shadow-sm">
          <div className="text-2xl font-bold text-slate-900">{count.toLocaleString("ar-EG")}</div>
          <div className="mt-1 text-xs text-slate-500">{label}</div>
        </div>
      ))}
    </div>
  );
}

function Section({
  title,
  children,
  loading,
}: {
  title: string;
  children: React.ReactNode;
  loading?: boolean;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-base font-bold text-slate-900">{title}</h2>
      {loading ? <Empty text="جارٍ التحميل…" /> : children}
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="py-6 text-center text-sm text-slate-400">{text}</div>;
}

function PersonChip({ id, name, subtitle }: { id: number; name: string; subtitle?: string }) {
  return (
    <Link
      to={`/persons/${id}`}
      className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm transition hover:border-slate-300 hover:bg-white"
    >
      <div className="font-medium text-slate-900">{name}</div>
      {subtitle && <div className="text-xs text-slate-500">{subtitle}</div>}
    </Link>
  );
}

function RelativeGroups({ groups }: { groups: [string, { id: number; full_name: string }[]][] }) {
  const present = groups.filter(([, items]) => items.length > 0);
  if (present.length === 0) return <Empty text="لا توجد علاقات قربى في هذه الفئة" />;
  return (
    <div className="space-y-3">
      {present.map(([label, items]) => (
        <div key={label}>
          <div className="mb-1.5 text-xs font-semibold text-slate-400">{label}</div>
          <div className="flex flex-wrap gap-2">
            {items.map((person) => (
              <PersonChip
                key={person.id}
                id={person.id}
                name={person.full_name}
                subtitle={(person as { relation?: string }).relation}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function genderLabel(gender: "M" | "F" | null): string {
  return gender === "M" ? "ذكر" : gender === "F" ? "أنثى" : "غير محدد";
}

function labelMarriage(status: string): string {
  const labels: Record<string, string> = {
    married: "زوج/زوجة",
    divorced: "مطلق",
    widowed: "أرمل",
  };
  return labels[status] ?? status;
}