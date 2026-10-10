import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { select, zoom, zoomIdentity, zoomTransform, type ZoomBehavior } from "d3";
import { api, errorMessage } from "../lib/api";
import type { Forest } from "../lib/types";
import { CHIP_H, layoutForest, type PlacedNode, type WorldLayout } from "../lib/forestLayout";
import { COL_W } from "../lib/treeLayout";
import PersonPicker from "../components/PersonPicker";

const COLORS = {
  male: { fill: "#eff6ff", stroke: "#3b82f6", text: "#1d4ed8" },
  female: { fill: "#fdf2f8", stroke: "#ec4899", text: "#be185d" },
  dead: { fill: "#f1f5f9", stroke: "#94a3b8", text: "#64748b" },
};
const EDGE = "#94a3b8";
const EDGE_SPOUSE = "#9aa8b8";
const HOVER = "#f59e0b";
const BG = "#f8fafc";

// Zoom-based LOD: far out everything collapses into dots, then edges + chips
// appear, then names, exactly like a zoomable map.
const LOD_DOTS = 13; // on-screen chip width below this → plain dots, no edges
const LOD_NAMES = 58; // chip width above this → show names & dates

export default function FullTreePage() {
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["forest"],
    queryFn: async () => {
      const { data } = await api.get<Forest>("/forest");
      return data;
    },
    staleTime: 60_000,
  });

  const world = useMemo<WorldLayout | null>(() => (query.data ? layoutForest(query.data) : null), [query.data]);

  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const zoomRef = useRef<ZoomBehavior<HTMLDivElement, unknown> | null>(null);
  const transformRef = useRef({ x: 0, y: 0, k: 1 });
  const hoverRef = useRef<PlacedNode | null>(null);
  const lastVisible = useRef<PlacedNode[]>([]);
  const drawRef = useRef<() => void>(() => {});
  const scaleElRef = useRef<HTMLSpanElement>(null);
  const dragging = useRef(false);

  const [hovered, setHovered] = useState<PlacedNode | null>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap || !world) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const cw = wrap.clientWidth;
    const ch = wrap.clientHeight;
    const pw = Math.floor(cw * dpr);
    const ph = Math.floor(ch * dpr);
    if (canvas.width !== pw || canvas.height !== ph) {
      canvas.width = pw;
      canvas.height = ph;
    }
    const { x, y, k } = transformRef.current;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, cw, ch);

    const vLeft = (0 - x) / k;
    const vTop = (0 - y) / k;
    const vRight = (cw - x) / k;
    const vBottom = (ch - y) / k;

    // Screen-space chip width decides which LOD we render.
    const chipW = COL_W * k;
    const dotMode = chipW < LOD_DOTS;

    // Cull nodes once; reused by edges, drawing and the hover hit-test.
    const visible: PlacedNode[] = [];
    for (const n of world.nodes) {
      if (n.x + n.w >= vLeft && n.x <= vRight && n.y + n.h >= vTop && n.y <= vBottom) visible.push(n);
    }
    lastVisible.current = visible;

    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * x, dpr * y);

    // ---- edges -------------------------------------------------------------
    if (!dotMode) {
      const pEdges = new Path2D();
      for (let i = 0; i < world.parentEdges.length; i += 4) {
        const x1 = world.parentEdges[i];
        const y1 = world.parentEdges[i + 1];
        const x2 = world.parentEdges[i + 2];
        const y2 = world.parentEdges[i + 3];
        if (Math.max(x1, x2) < vLeft || Math.min(x1, x2) > vRight || Math.max(y1, y2) < vTop || Math.min(y1, y2) > vBottom) continue;
        const midY = (y1 + y2) / 2;
        pEdges.moveTo(x1, y1);
        pEdges.bezierCurveTo(x1, midY, x2, midY, x2, y2);
      }
      ctx.strokeStyle = EDGE;
      ctx.lineWidth = 1.8 / k;
      ctx.lineCap = "round";
      ctx.stroke(pEdges);

      const sEdges = new Path2D();
      for (let i = 0; i < world.spouseEdges.length; i += 4) {
        const x1 = world.spouseEdges[i];
        const y1 = world.spouseEdges[i + 1];
        const x2 = world.spouseEdges[i + 2];
        const y2 = world.spouseEdges[i + 3];
        if (Math.max(x1, x2) < vLeft || Math.min(x1, x2) > vRight || Math.max(y1, y2) < vTop || Math.min(y1, y2) > vBottom) continue;
        sEdges.moveTo(x1, y1);
        sEdges.lineTo(x2, y2);
      }
      ctx.strokeStyle = EDGE_SPOUSE;
      ctx.lineWidth = 2 / k;
      ctx.stroke(sEdges);
    }

    // ---- nodes --------------------------------------------------------------
    if (dotMode) {
      // Thousands of nodes are visible here — batch into one path + single fill.
      const dots = new Path2D();
      for (const n of visible) dots.rect(n.x, n.y, n.w, n.h);
      ctx.fillStyle = "#94a3b8";
      ctx.fill(dots);
    } else {
      const male = new Path2D();
      const female = new Path2D();
      const dead = new Path2D();
      for (const n of visible) {
        const alive = !n.person.death_date;
        const bucket = n.person.gender === "F" && alive ? female : alive ? male : dead;
        roundRect(bucket, n.x, n.y, n.w, n.h, 10 / k);
      }
      ctx.strokeStyle = COLORS.male.stroke;
      ctx.lineWidth = 1.4 / k;
      ctx.fillStyle = COLORS.male.fill;
      ctx.fill(male);
      ctx.stroke(male);
      ctx.strokeStyle = COLORS.female.stroke;
      ctx.fillStyle = COLORS.female.fill;
      ctx.fill(female);
      ctx.stroke(female);
      ctx.strokeStyle = COLORS.dead.stroke;
      ctx.fillStyle = COLORS.dead.fill;
      ctx.fill(dead);
      ctx.stroke(dead);
    }

    // ---- flying labels (screen space, constant size like a map) -----------
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!dotMode && chipW >= LOD_NAMES) {
      for (const n of visible) {
        const sx = n.x * k + x;
        const sy = n.y * k + y;
        const w = n.w * k;
        const h = n.h * k;
        const palette = n.person.death_date
          ? COLORS.dead
          : n.person.gender === "F"
            ? COLORS.female
            : COLORS.male;
        ctx.font = "600 11px Cairo, sans-serif";
        ctx.fillStyle = palette.text;
        ctx.direction = "rtl";
        const name = fitText(ctx, n.person.full_name, w - 14);
        if (name) ctx.fillText(name, sx + w / 2, sy + 16);
        if (h >= 40 && n.person.birth_date) {
          ctx.font = "10px Cairo, sans-serif";
          ctx.fillStyle = "#64748b";
          ctx.direction = "ltr";
          const range = n.person.death_date ? `${n.person.birth_date} – ${n.person.death_date}` : n.person.birth_date;
          ctx.fillText(range, sx + w / 2, sy + h - 9);
        }
      }
    }

    // Hover ring.
    const ho = hoverRef.current;
    if (ho) {
      const sx = ho.x * k + x;
      const sy = ho.y * k + y;
      ctx.strokeStyle = HOVER;
      ctx.lineWidth = 2.5;
      roundRectScreen(ctx, sx - 2, sy - 2, COL_W * k + 4, CHIP_H * k + 4, 8);
      ctx.stroke();
    }
  }, [world]);

  useEffect(() => {
    drawRef.current = draw;
  });

  const applyTransform = useCallback((t: { x: number; y: number; k: number }) => {
    const wrap = wrapRef.current;
    if (!zoomRef.current || !wrap) return;
    select(wrap).call(zoomRef.current.transform, zoomIdentity.translate(t.x, t.y).scale(t.k));
  }, []);

  // d3-zoom drives pan/zoom; draw imperatively (no React re-render per frame).
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const behavior = zoom<HTMLDivElement, unknown>()
      .scaleExtent([0.002, 8])
      .clickDistance(3)
      .on("zoom", (event) => {
        transformRef.current = { x: event.transform.x, y: event.transform.y, k: event.transform.k };
        drawRef.current();
        if (scaleElRef.current) scaleElRef.current.textContent = `${Math.round(event.transform.k * 100)}%`;
      });
    zoomRef.current = behavior;
    select(wrap).call(behavior);
    return () => {
      select(wrap).on(".zoom", null);
    };
  }, []);

  const fitAll = useCallback(() => {
    if (!world || !wrapRef.current) return;
    const cw = wrapRef.current.clientWidth;
    const ch = wrapRef.current.clientHeight;
    const k = Math.min((cw - 40) / world.width, (ch - 40) / world.height, 1);
    const x = (cw - world.width * k) / 2;
    const y = (ch - world.height * k) / 2;
    applyTransform({ x, y, k });
  }, [world, applyTransform]);

  useEffect(() => {
    if (world) fitAll();
  }, [world, fitAll]);

  const stepZoom = useCallback(
    (factor: number) => {
      const wrap = wrapRef.current;
      if (!wrap) return;
      const current = zoomTransform(wrap);
      const k = Math.min(8, Math.max(0.01, current.k * factor));
      const cw = wrap.clientWidth;
      const ch = wrap.clientHeight;
      const x = cw / 2 - ((cw / 2 - current.x) * k) / current.k;
      const y = ch / 2 - ((ch / 2 - current.y) * k) / current.k;
      applyTransform({ x, y, k });
    },
    [applyTransform],
  );

  const centerOn = useCallback(
    (node: PlacedNode) => {
      const wrap = wrapRef.current;
      if (!wrap) return;
      const k = 1;
      const x = wrap.clientWidth / 2 - (node.x + node.w / 2) * k;
      const y = wrap.clientHeight / 2 - (node.y + node.h / 2) * k;
      applyTransform({ x, y, k });
    },
    [applyTransform],
  );

  const pointerToWorld = useCallback((e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const { x, y, k } = transformRef.current;
    return { x: (e.clientX - rect.left - x) / k, y: (e.clientY - rect.top - y) / k };
  }, []);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (dragging.current) return;
      const wp = pointerToWorld(e);
      if (!wp) return;
      let found: PlacedNode | null = null;
      for (const n of lastVisible.current) {
        if (wp.x >= n.x && wp.x <= n.x + n.w && wp.y >= n.y && wp.y <= n.y + n.h) {
          found = n;
          break;
        }
      }
      if ((found?.person.id ?? 0) !== (hoverRef.current?.person.id ?? 0)) {
        hoverRef.current = found;
        drawRef.current();
        setHovered(found);
      }
    },
    [pointerToWorld],
  );

  const onPointerLeave = useCallback(() => {
    hoverRef.current = null;
    drawRef.current();
    setHovered(null);
  }, []);

  if (query.isError) {
    return <div className="text-red-600">{errorMessage(query.error)}</div>;
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">الشجرة الكاملة للجميع</h1>
          <p className="mt-1 text-sm text-slate-500">
            {world
              ? `${world.nodes.length.toLocaleString("ar-EG")} شخص في ${world.components.toLocaleString("ar-EG")} عائلة — اسحب واستكشف أو اضغط على أي شخص لعرضه`
              : "جارٍ تجهيز الخريطة…"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="w-64">
            <PersonPicker
              label=""
              value={null}
              placeholder="…اذهب إلى شخص معيّن"
              onChange={(person) => {
                const node = person ? world?.posById.get(person.id) : undefined;
                if (node) centerOn(node);
              }}
            />
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => stepZoom(1.4)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              aria-label="تكبير"
              title="تكبير"
            >
              +
            </button>
            <button
              type="button"
              onClick={() => stepZoom(1 / 1.4)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              aria-label="تصغير"
              title="تصغير"
            >
              −
            </button>
            <button
              type="button"
              onClick={fitAll}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              عرض الكل
            </button>
            <span
              ref={scaleElRef}
              className="min-w-12 rounded-lg bg-slate-900 px-2 py-1.5 text-center text-xs font-semibold text-white"
            >
              100%
            </span>
          </div>
        </div>
      </header>

      <div
        ref={wrapRef}
        className="relative h-[78vh] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
        dir="ltr"
      >
        <canvas
          ref={canvasRef}
          className="h-full w-full cursor-grab active:cursor-grabbing"
          onPointerMove={onPointerMove}
          onPointerLeave={onPointerLeave}
          onPointerDown={() => (dragging.current = true)}
          onPointerUp={() => {
            dragging.current = false;
          }}
          onClick={(e) => {
            const wp = pointerToWorld(e as unknown as React.PointerEvent);
            if (!wp || dragging.current) return;
            for (const n of lastVisible.current) {
              if (wp.x >= n.x && wp.x <= n.x + n.w && wp.y >= n.y && wp.y <= n.y + n.h) {
                navigate(`/persons/${n.person.id}`);
                return;
              }
            }
          }}
        />
        {(query.isPending || !world) && (
          <div className="absolute inset-0 flex items-center justify-center bg-white text-slate-500">
            جارٍ تحميل كل الأشخاص وتجهيز الخريطة…
          </div>
        )}
        {hovered && (
          <div
            className="pointer-events-none absolute right-3 top-3 z-10 max-w-xs rounded-xl bg-slate-900 px-4 py-3 text-sm text-white shadow-xl"
            dir="rtl"
          >
            <div className="font-semibold">{hovered.person.full_name}</div>
            <div className="mt-1 flex flex-wrap gap-1 text-xs text-slate-300">
              <span>{hovered.person.gender === "F" ? "أنثى" : "ذكر"}</span>
              <span className="ltr">{hovered.person.birth_date ?? "؟"}</span>
              {hovered.person.death_date && <span className="ltr">— {hovered.person.death_date}</span>}
            </div>
            <div className="mt-1 text-[11px] text-emerald-300">اضغط لعرض الملف الكامل</div>
          </div>
        )}
        <div
          className="pointer-events-none absolute bottom-3 left-3 rounded-lg bg-white/90 px-3 py-1.5 text-xs text-slate-500 shadow-sm ring-1 ring-slate-200"
          dir="rtl"
        >
          اسحب للتحريك · عجلة الفأرة للتكبير أو الأزرار +/− · تقترب الأسماء كلما كبّرت
        </div>
      </div>
    </div>
  );
}

function roundRect(p: Path2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  p.moveTo(x + rr, y);
  p.arcTo(x + w, y, x + w, y + h, rr);
  p.arcTo(x + w, y + h, x, y + h, rr);
  p.arcTo(x, y + h, x, y, rr);
  p.arcTo(x, y, x + w, y, rr);
  p.closePath();
}

function roundRectScreen(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  const rr = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function fitText(ctx: CanvasRenderingContext2D, text: string, maxW: number) {
  if (maxW <= 0 || !text) return "";
  if (ctx.measureText(text).width <= maxW) return text;
  let t = text;
  while (t.length > 1 && ctx.measureText(t + "…").width > maxW) t = t.slice(0, -1);
  return t + "…";
}