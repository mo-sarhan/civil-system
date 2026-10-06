import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { select, zoom, zoomIdentity, zoomTransform, type ZoomBehavior } from "d3";
import { api, errorMessage } from "../lib/api";
import type { FamilyTree, Person, TreeNode } from "../lib/types";
import { COL_GAP, COL_W, ROW_GAP, ROW_H, layoutTree } from "../lib/treeLayout";
import PersonPicker from "../components/PersonPicker";

const PAD = 24;
const CHIP_H = 64;
const CHIP_RADIUS = 12;

const PATH_COLORS = {
  start: "#059669",
  end: "#dc2626",
  mid: "#d97706",
};
const PATH_EDGE_COLOR = "#f59e0b";

export default function FamilyTreePage() {
  const { personId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const fromParam = personId ? Number(personId) : Number(searchParams.get("person_id") ?? 0);

  const pathIds = useMemo(
    () =>
      (searchParams.get("path") ?? "")
        .split(",")
        .map((s) => Number(s))
        .filter((n) => Number.isInteger(n) && n > 0),
    [searchParams],
  );
  const pathRelation = searchParams.get("rel");
  const pathDegree = searchParams.get("deg") ? Number(searchParams.get("deg")) : null;
  const isPathOn = pathIds.length >= 2;

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

  const { posById, pathRole, pathPairs, pathVisible } = useMemo(() => {
    const pos = new Map<number, { col: number; row: number }>();
    const parentSet = new Set<string>();
    const spouseSet = new Set<string>();
    if (layout) {
      for (const row of layout.rows) {
        for (const n of row) pos.set(n.person.id, { col: n.col, row: n.row });
      }
      for (const [p, c] of layout.parentEdges) parentSet.add(`${p},${c}`);
      for (const [a, b] of layout.spousePairs) spouseSet.add(`${a},${b}`);
    }
    const role = new Map<number, "start" | "end" | "mid">();
    pathIds.forEach((id, i) => {
      if (i === 0) role.set(id, "start");
      else if (i === pathIds.length - 1) role.set(id, "end");
      else role.set(id, "mid");
    });
    const pairs: { u: number; v: number; kind: "parent" | "spouse" }[] = [];
    for (let i = 0; i + 1 < pathIds.length; i++) {
      const u = pathIds[i];
      const v = pathIds[i + 1];
      if (parentSet.has(`${u},${v}`) || parentSet.has(`${v},${u}`)) {
        pairs.push({ u, v, kind: "parent" });
      } else if (spouseSet.has(`${u},${v}`) || spouseSet.has(`${v},${u}`)) {
        pairs.push({ u, v, kind: "spouse" });
      }
    }
    return {
      posById: pos,
      pathRole: role,
      pathPairs: pairs,
      pathVisible: pathIds.filter((id) => pos.has(id)),
    };
  }, [layout, pathIds]);

  const svgRef = useRef<SVGSVGElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const zoomGRef = useRef<SVGGElement>(null);
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;
    const behavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 3])
      .on("zoom", (event) => {
        if (zoomGRef.current) {
          select(zoomGRef.current).attr("transform", event.transform.toString());
        }
      });
    zoomRef.current = behavior;
    select(svgEl).call(behavior);
    return () => {
      select(svgEl).on(".zoom", null);
    };
  }, []);

  const applyTransform = useCallback((transform: { x: number; y: number; k: number }) => {
    if (!zoomRef.current || !svgRef.current) return;
    select(svgRef.current).call(zoomRef.current.transform, zoomIdentity.translate(transform.x, transform.y).scale(transform.k));
  }, []);

  const centerView = useCallback(() => {
    if (!layout) return;
    const containerW = wrapRef.current?.clientWidth ?? 800;
    const k = Math.min(1, (containerW - 32) / layout.width);
    const x = Math.max(PAD, (containerW - layout.width * k) / 2);
    applyTransform({ x, y: PAD, k });
  }, [layout, applyTransform]);

  const stepZoom = useCallback(
    (factor: number) => {
      if (!svgRef.current || !wrapRef.current) return;
      const current = zoomTransform(svgRef.current);
      const k = Math.min(3, Math.max(0.2, current.k * factor));
      const containerW = wrapRef.current.clientWidth;
      const containerH = wrapRef.current.clientHeight;
      const x = containerW / 2 - ((containerW / 2 - current.x) * k) / current.k;
      const y = containerH / 2 - ((containerH / 2 - current.y) * k) / current.k;
      applyTransform({ x, y, k });
    },
    [applyTransform],
  );

  // Frame the highlighted path so it fills most of the viewport.
  const framePath = useCallback(() => {
    if (!layout || pathIds.length === 0) return;
    const pts: { x: number; y: number }[] = [];
    for (const row of layout.rows) {
      for (const n of row) {
        if (pathIds.includes(n.person.id)) {
          pts.push({ x: colX(n.col), y: rowY(n.row) });
        }
      }
    }
    if (pts.length < 2) return;
    const containerW = wrapRef.current?.clientWidth ?? 800;
    const containerH = wrapRef.current?.clientHeight ?? 600;
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of pts) {
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x + COL_W);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y + CHIP_H);
    }
    const pad = 56;
    const k = Math.max(
      0.25,
      Math.min(1, containerW / (maxX - minX + pad * 2), containerH / (maxY - minY + pad * 2)),
    );
    const x = (containerW - (maxX - minX) * k) / 2 - minX * k;
    const y = (containerH - (maxY - minY) * k) / 2 - minY * k;
    applyTransform({ x, y, k });
  }, [layout, pathIds, applyTransform]);

  const clearPath = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete("path");
      next.delete("rel");
      next.delete("deg");
      return next;
    });
  }, [setSearchParams]);

  // Centre the tree when new data arrives.
  useEffect(() => {
    centerView();
  }, [centerView]);

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
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => stepZoom(1.3)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              aria-label="تكبير"
              title="تكبير"
            >
              +
            </button>
            <button
              type="button"
              onClick={() => stepZoom(1 / 1.3)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              aria-label="تصغير"
              title="تصغير"
            >
              −
            </button>
            <button
              type="button"
              onClick={centerView}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              توسيط
            </button>
          </div>
        </div>
      </header>

      {isPathOn && (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 shadow-sm"
          dir="rtl"
        >
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-semibold text-amber-800">مسار مُوضَّح على الشجرة</span>
            {pathRelation && <span className="text-sm text-amber-700">{pathRelation}</span>}
            {pathDegree !== null && (
              <span className="rounded bg-white px-2 py-0.5 text-xs font-semibold text-amber-700 ring-1 ring-amber-200">
                درجة القرابة: {pathDegree}
              </span>
            )}
            {pathVisible.length < pathIds.length && (
              <span className="text-xs text-amber-600">
                ظاهر: {pathVisible.length}/{pathIds.length}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            {pathVisible.length >= 2 && (
              <button
                type="button"
                onClick={framePath}
                className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
              >
                توسيط المسار
              </button>
            )}
            <button
              type="button"
              onClick={clearPath}
              className="rounded-lg border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-100"
            >
              مسح التظليل
            </button>
          </div>
        </div>
      )}

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
          <g ref={zoomGRef}>
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

            {pathPairs.length > 0 && (
              <g>
                {pathPairs.map(({ u, v, kind }) => {
                  const A = posById.get(u);
                  const B = posById.get(v);
                  if (!A || !B) return null;
                  if (kind === "spouse") {
                    const y = rowY(A.row) + CHIP_H + 10;
                    const x1 = colX(A.col) + COL_W / 2;
                    const x2 = colX(B.col) + COL_W / 2;
                    return (
                      <path
                        key={`pth-${u}-${v}`}
                        d={`M${x1},${y} L${x2},${y}`}
                        stroke={PATH_EDGE_COLOR}
                        strokeWidth="5"
                        strokeLinecap="round"
                      />
                    );
                  }
                  const P = A.row <= B.row ? A : B;
                  const C = A.row <= B.row ? B : A;
                  const x1 = colX(P.col) + COL_W / 2;
                  const y1 = rowY(P.row) + CHIP_H;
                  const x2 = colX(C.col) + COL_W / 2;
                  const y2 = rowY(C.row);
                  const midY = (y1 + y2) / 2;
                  return (
                    <path
                      key={`pth-${u}-${v}`}
                      d={`M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`}
                      fill="none"
                      stroke={PATH_EDGE_COLOR}
                      strokeWidth="5"
                      strokeLinecap="round"
                    />
                  );
                })}
              </g>
            )}

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
                      pathRole={pathRole.get(person.id)}
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
          اسحب للتحريك · عجلة الفأرة للتكبير أو الأزرار +/− · انقر على شخص لتوسيط الشجرة عليه
        </div>
        {isPathOn && (
          <div
            className="pointer-events-none absolute bottom-3 right-3 flex flex-wrap items-center gap-3 rounded-lg bg-white/90 px-3 py-1.5 text-[11px] text-slate-600 shadow-sm ring-1 ring-slate-200"
            dir="rtl"
          >
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: PATH_COLORS.start }} />
              بداية المسار
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: PATH_COLORS.mid }} />
              منتصف المسار
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: PATH_COLORS.end }} />
              نهاية المسار
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1 w-4 rounded" style={{ background: PATH_EDGE_COLOR }} />
              رابطة المسار
            </span>
          </div>
        )}
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
  pathRole,
  onHover,
  onClick,
  link,
}: {
  node: TreeNode;
  x: number;
  y: number;
  isSubject: boolean;
  highlighted: boolean;
  pathRole?: "start" | "end" | "mid";
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

  const pathColor = pathRole ? PATH_COLORS[pathRole] : null;
  const chipStroke = pathColor ?? (alive ? stroke : deceasedStroke);
  const chipStrokeWidth = pathColor ? 3.5 : isSubject ? 3 : 1.5;

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
        stroke={chipStroke}
        strokeWidth={chipStrokeWidth}
        className="transition-opacity"
        opacity={highlighted ? 0.55 : 1}
      />
      {pathColor && (
        <rect
          x={-4}
          y={-4}
          width={COL_W + 8}
          height={CHIP_H + 8}
          rx={CHIP_RADIUS + 3}
          fill="none"
          stroke={pathColor}
          strokeWidth={2}
          strokeDasharray="5 4"
        />
      )}
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