import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { select, zoom, zoomIdentity, type ZoomBehavior } from "d3";
import { api, errorMessage } from "../lib/api";
import type { FamilyTree, Person, TreeNode } from "../lib/types";
import { COL_GAP, COL_W, ROW_GAP, ROW_H, layoutTree } from "../lib/treeLayout";
import PersonPicker from "../components/PersonPicker";

const PAD = 24;
const CHIP_H = 64;
const CHIP_RADIUS = 12;

export default function FamilyTreePage() {
  const { personId } = useParams();
  const [searchParams] = useSearchParams();
  const fromParam = personId ? Number(personId) : Number(searchParams.get("person_id") ?? 0);

  // When the route has no id, default to the first person so /tree is usable
  // straight from the sidebar.
  const firstPerson = useQuery({
    queryKey: ["persons", "first"],
    queryFn: async () => {
      const { data } = await api.get<{ items: Person[] }>("/persons?page_size=1&sort=id&direction=asc");
      return data.items[0];
    },
    enabled: fromParam === 0,
  });

  const targetId = fromParam > 0 ? fromParam : firstPerson.data?.id ?? 0;

  const treeQuery = useQuery({
    queryKey: ["tree", targetId],
    queryFn: async () => {
      const { data } = await api.get<FamilyTree>(`/persons/${targetId}/tree`);
      return data;
    },
    enabled: targetId > 0,
  });

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const subject =
    selectedId != null ? (treeQuery.data?.nodes.find((n) => n.id === selectedId) ?? null) : null;

  const layout = treeQuery.data ? layoutTree(treeQuery.data) : null;

  const svgRef = useRef<SVGSVGElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const [view, setView] = useState({ x: PAD, y: PAD, k: 1 });

  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;
    const behavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 3])
      .on("zoom", (event) => setView(event.transform));
    zoomRef.current = behavior;
    select(svgEl).call(behavior);
    return () => {
      select(svgEl).on(".zoom", null);
    };
  }, []);

  // Centre the tree when new data arrives.
  useEffect(() => {
    if (!layout || !wrapRef.current) return;
    const containerW = wrapRef.current.clientWidth;
    const k = Math.min(1, (containerW - 32) / layout.width);
    const x = Math.max(PAD, (containerW - layout.width * k) / 2);
    const next = { x, y: PAD, k };
    setView(next);
    if (zoomRef.current && svgRef.current) {
      select(svgRef.current).call(
      zoomRef.current.transform,
      zoomIdentity.translate(next.x, next.y).scale(next.k),
    );
    }
  }, [layout]);

  const [hoverId, setHoverId] = useState<number | null>(null);
  const hovered = hoverId ? treeQuery.data?.nodes.find((n) => n.id === hoverId) : null;

  if (treeQuery.isError) {
    return <div className="text-red-600">{errorMessage(treeQuery.error)}</div>;
  }
  if (treeQuery.isPending || !layout || !treeQuery.data) {
    return <div className="text-slate-500">جارٍ تحميل الشجرة…</div>;
  }
  const tree = treeQuery.data;

  const toggleSubject = (id: number) => setSelectedId((prev) => (prev === id ? null : id));

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">شجرة العائلة</h1>
          <p className="mt-1 text-sm text-slate-500">
            {subject ? `معروض حول: ${subject.full_name}` : tree.truncated
              ? "الشجرة مقتطعة — بعض الفروع اختُصرت"
              : `${tree.total_nodes} شخص في النطاق المعروض`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-64">
            <PersonPicker
              label=""
              value={selectedId ?? targetId}
              placeholder="…ابحث عن شخص لتوسيط الشجرة عليه"
              onChange={(person) => {
                if (person) {
                  setSelectedId(person.id);
                  window.history.replaceState(null, "", `/tree?person_id=${person.id}`);
                }
              }}
            />
          </div>
          <button
            type="button"
            onClick={() => {
              const k = Math.min(1, ((wrapRef.current?.clientWidth ?? 800) - 32) / layout.width);
              const x = Math.max(PAD, ((wrapRef.current?.clientWidth ?? 800) - layout.width * k) / 2);
              const next = { x, y: PAD, k };
              setView(next);
              if (zoomRef.current && svgRef.current) {
                select(svgRef.current).call(
                  zoomRef.current.transform,
                  zoomIdentity.translate(next.x, next.y).scale(next.k),
                );
              }
            }}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            توسيط
          </button>
        </div>
      </header>

      {hovered && hovered.id !== (subject?.id ?? targetId) && (
        <MiniCard node={hovered} />
      )}

      <div
        ref={wrapRef}
        className="relative h-[75vh] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
        dir="ltr"
      >
        <svg
          ref={svgRef}
          width="100%"
          height="100%"
          className="cursor-grab active:cursor-grabbing"
        >
          <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
            <g>
              {layout.spousePairs.map(([a, b]) => {
                const A = layout.rows.flat().find((n) => n.person.id === a);
                const B = layout.rows.flat().find((n) => n.person.id === b);
                if (!A || !B) return null;
                const y = rowY(A.row) + CHIP_H + 10;
                const x1 = colX(A.col) + COL_W / 2;
                const x2 = colX(B.col) + COL_W / 2;
                return <path key={`sp-${a}-${b}`} d={`M${x1},${y} L${x2},${y}`} stroke="#94a3b8" strokeWidth="2" />;
              })}
              {layout.parentEdges.map(([parentId, childId]) => {
                const P = layout.rows.flat().find((n) => n.person.id === parentId);
                const C = layout.rows.flat().find((n) => n.person.id === childId);
                if (!P || !C) return null;
                const x1 = colX(P.col) + COL_W / 2;
                const y1 = rowY(P.row) + CHIP_H;
                const x2 = colX(C.col) + COL_W / 2;
                const y2 = rowY(C.row);
                const midY = (y1 + y2) / 2;
                return (
                  <path
                    key={`par-${parentId}-${childId}`}
                    d={`M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`}
                    fill="none"
                    stroke="#94a3b8"
                    strokeWidth="1.8"
                  />
                );
              })}
            </g>

            <g>
              {layout.rows.map((row) => (
                <g key={row[0].row}>
                  {row.map(({ person, col }) => (
                    <Chip
                      key={person.id}
                      node={person}
                      x={colX(col)}
                      y={rowY(row[0].row)}
                      isSubject={person.id === (subject?.id ?? targetId)}
                      highlighted={person.id === hoverId}
                      onHover={setHoverId}
                      onClick={() => toggleSubject(person.id)}
                      link={({ children }) => (
                        <Link
                          to={`/persons/${person.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-slate-900 hover:underline"
                        >
                          {children}
                        </Link>
                      )}
                    />
                  ))}
                </g>
              ))}
            </g>
          </g>
        </svg>
        <div className="pointer-events-none absolute bottom-3 left-3 rounded-lg bg-white/90 px-3 py-1.5 text-xs text-slate-500 shadow-sm ring-1 ring-slate-200" dir="rtl">
          اسحب للتحريك · عجلة الفأرة للتكبير · انقر على شخص لتوسيط الشجرة عليه
        </div>
      </div>
    </div>
  );
}

const rowY = (row: number) => PAD + row * (ROW_H + ROW_GAP);
const colX = (col: number) => col * (COL_W + COL_GAP);

const truncate = (text: string, max: number) => (text.length > max ? `${text.slice(0, max)}…` : text);

function Chip({
  node,
  x,
  y,
  isSubject,
  highlighted,
  onHover,
  onClick,
  link,
}: {
  node: TreeNode;
  x: number;
  y: number;
  isSubject: boolean;
  highlighted: boolean;
  onHover: (id: number) => void;
  onClick: () => void;
  link: (props: { children: React.ReactNode }) => React.ReactNode;
}) {
  const female = node.gender === "F";
  const alive = !node.death_date;
  const fill = female ? "#fdf2f8" : "#eff6ff";
  const stroke = female ? "#ec4899" : "#3b82f6";
  const deceasedFill = "#f1f5f9";
  const deceasedStroke = "#94a3b8";

  return (
    <g
      transform={`translate(${x},${y})`}
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={() => onHover(0)}
      onClick={onClick}
      style={{ cursor: "pointer" }}
    >
      {(node.has_more_parents || node.has_more_children) && (
        <g>
          {node.has_more_parents && (
            <line x1={COL_W / 2} y1={-18} x2={COL_W / 2} y2={-4} stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="3 3" />
          )}
          {node.has_more_children && (
            <line x1={COL_W / 2} y1={CHIP_H + 4} x2={COL_W / 2} y2={CHIP_H + 18} stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="3 3" />
          )}
        </g>
      )}
      <rect
        x={0}
        y={0}
        width={COL_W}
        height={CHIP_H}
        rx={CHIP_RADIUS}
        fill={alive ? fill : deceasedFill}
        stroke={alive ? stroke : deceasedStroke}
        strokeWidth={isSubject ? 3 : 1.5}
        className="transition-opacity"
        opacity={highlighted ? 0.55 : 1}
      />
      <foreignObject x={6} y={8} width={COL_W - 12} height={30}>
        <div
          dir="rtl"
          className="flex h-full items-center justify-center overflow-hidden text-[13px] font-semibold leading-tight text-slate-900"
        >
          {link({ children: truncate(node.full_name, 22) })}
        </div>
      </foreignObject>
      <text
        x={COL_W / 2}
        y={CHIP_H - 12}
        textAnchor="middle"
        className="fill-slate-500"
        style={{ fontSize: 11, direction: "ltr", unicodeBidi: "embed" }}
      >
        {node.birth_date ? node.birth_date : (alive ? "?—" : "")}
        {node.death_date ? ` – ${node.death_date}` : ""}
      </text>
      {isSubject && (
        <text
          x={COL_W / 2}
          y={-30 + 12}
          textAnchor="middle"
          className="fill-amber-600"
          style={{ fontSize: 11, fontWeight: 700 }}
        >
          أنت هنا
        </text>
      )}
    </g>
  );
}

function MiniCard({ node }: { node: TreeNode }) {
  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-30 max-w-xs rounded-xl bg-slate-900 px-4 py-3 text-sm text-white shadow-xl" dir="rtl">
      <div className="font-semibold">{node.full_name}</div>
      <div className="mt-1 flex flex-wrap gap-1 text-xs text-slate-300">
        <span className="ltr">{node.birth_date ?? "?"}</span>
        {node.death_date && <span className="ltr">— {node.death_date}</span>}
        {node.birth_place && <span>· {node.birth_place}</span>}
      </div>
    </div>
  );
}