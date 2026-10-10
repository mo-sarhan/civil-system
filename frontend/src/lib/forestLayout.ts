import type { FamilyTree } from "./types";
import type { Forest, ForestPerson } from "./types";
import { COL_GAP, COL_W, ROW_GAP, ROW_H, layoutTree } from "./treeLayout";

/**
 * Lay out the WHOLE dataset as one giant navigable map.
 *
 * The civil registry is a forest of families (each household is its own
 * connected component), so we:
 *   1. split people into connected components over parent/child + marriage,
 *   2. run the same couple-aware tidy layout used by the focused tree on each
 *      component (with a synthetic ``depth`` = generation below the founders),
 *   3. pack the components into a uniform grid of world coordinates.
 *
 * The result is a flat position list + edge lists the canvas renderer can
 * cull against, so 50k+ people render smoothly like a zoomable map.
 */

export const CHIP_H = 64; // must match FamilyTreePage chip height
const PAD = 24;
const GRID_GAP_X = 110;
const GRID_GAP_Y = 110;
const CELL_PAD_TOP = 24;

export interface PlacedNode {
  person: ForestPerson;
  x: number; // world px
  y: number;
  w: number;
  h: number;
}

export interface WorldLayout {
  nodes: PlacedNode[];
  posById: Map<number, PlacedNode>;
  /** Flattened [x1, y1, x2, y2, …] world coordinates. */
  parentEdges: number[];
  spouseEdges: number[];
  width: number;
  height: number;
  components: number;
}

const colX = (col: number) => col * (COL_W + COL_GAP);
const rowY = (row: number) => PAD + row * (ROW_H + ROW_GAP);

class UnionFind {
  private parent: Int32Array;

  constructor(size: number) {
    this.parent = new Int32Array(size);
    for (let i = 0; i < size; i++) this.parent[i] = i;
  }

  find(x: number): number {
    let root = x;
    while (this.parent[root] !== root) root = this.parent[root];
    while (this.parent[x] !== x) {
      const next = this.parent[x];
      this.parent[x] = root;
      x = next;
    }
    return root;
  }

  union(a: number, b: number): void {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) this.parent[rb] = ra;
  }
}

/** Generation per person: founders = 0, spouses share the row, children ↓. */
function computeGenerations(
  comp: ForestPerson[],
  memberIds: Set<number>,
  compMarriages: [number, number][],
): Map<number, number> {
  const gen = new Map<number, number>();
  const spouseOf = new Map<number, number>();
  for (const [h, w] of compMarriages) {
    if (!spouseOf.has(h)) spouseOf.set(h, w);
    if (!spouseOf.has(w)) spouseOf.set(w, h);
  }
  const parentsIn = (p: ForestPerson): number[] =>
    [p.father_id, p.mother_id].filter((x): x is number => x != null && memberIds.has(x));

  for (const p of comp) if (parentsIn(p).length === 0) gen.set(p.id, 0);

  let passes = comp.length + 2;
  let changed = true;
  while (changed && passes-- > 0) {
    changed = false;
    for (const p of comp) {
      if (gen.has(p.id)) continue;
      const sp = spouseOf.get(p.id);
      if (sp != null && gen.has(sp)) {
        gen.set(p.id, gen.get(sp)!);
        changed = true;
        continue;
      }
      const pg = parentsIn(p)
        .map((x) => gen.get(x))
        .filter((g): g is number => g != null);
      if (pg.length > 0) {
        gen.set(p.id, Math.max(...pg) + 1);
        changed = true;
      }
    }
  }

  const missing = comp.filter((p) => !gen.has(p.id));
  if (missing.length > 0) {
    const adj = new Map<number, number[]>();
    const link = (a: number, b: number) => {
      let arr = adj.get(a);
      if (!arr) adj.set(a, (arr = []));
      arr.push(b);
    };
    for (const p of comp) {
      for (const par of [p.father_id, p.mother_id]) {
        if (par != null && memberIds.has(par)) {
          link(p.id, par);
          link(par, p.id);
        }
      }
    }
    for (const [h, w] of compMarriages) {
      link(h, w);
      link(w, h);
    }
    const queue: number[] = [];
    for (const p of comp) if (gen.has(p.id)) queue.push(p.id);
    for (let qi = 0; qi < queue.length; qi++) {
      const cur = queue[qi];
      const d = gen.get(cur)!;
      for (const nb of adj.get(cur) ?? []) {
        if (!gen.has(nb)) {
          gen.set(nb, d + 1);
          queue.push(nb);
        }
      }
    }
  }
  for (const p of comp) if (!gen.has(p.id)) gen.set(p.id, 0);
  return gen;
}

export function layoutForest(forest: Forest): WorldLayout {
  const persons: ForestPerson[] = forest.nodes.map((t) => ({
    id: t[0],
    full_name: t[1],
    gender: t[2],
    birth_date: t[3],
    death_date: t[4],
    father_id: t[5],
    mother_id: t[6],
  }));
  const byId = new Map<number, ForestPerson>();
  let maxId = 0;
  for (const p of persons) {
    byId.set(p.id, p);
    if (p.id > maxId) maxId = p.id;
  }

  const uf = new UnionFind(maxId + 1);
  for (const p of persons) {
    if (p.father_id != null) uf.union(p.id, p.father_id);
    if (p.mother_id != null) uf.union(p.id, p.mother_id);
  }
  for (const [h, w] of forest.marriages) uf.union(h, w);

  const groups = new Map<number, number[]>();
  for (const p of persons) {
    const r = uf.find(p.id);
    let arr = groups.get(r);
    if (!arr) groups.set(r, (arr = []));
    arr.push(p.id);
  }
  const components = [...groups.values()];

  // Index marriages by component once (not once per component!).
  const marriagesByComp = new Map<number, [number, number][]>();
  for (const [h, w] of forest.marriages) {
    const r = uf.find(h);
    let arr = marriagesByComp.get(r);
    if (!arr) marriagesByComp.set(r, (arr = []));
    arr.push([h, w]);
  }

  interface Pending {
    nodes: PlacedNode[];
    parent: number[];
    spouse: number[];
    w: number;
    h: number;
  }
  const pending: Pending[] = [];

  for (const comp of components) {
    const memberIds = new Set(comp);
    const compPersons = comp.map((id) => byId.get(id)!);
    const compMarriages = marriagesByComp.get(uf.find(comp[0])) ?? [];
    const gen = computeGenerations(compPersons, memberIds, compMarriages);

    const nodes = compPersons.map((p) => ({
      id: p.id,
      depth: gen.get(p.id)!,
      generation: "",
      full_name: p.full_name,
      gender: p.gender,
      birth_date: p.birth_date,
      death_date: p.death_date,
      birth_place: null,
      father_id: p.father_id,
      mother_id: p.mother_id,
      has_more_parents: false,
      has_more_children: false,
      children: [] as number[],
    }));
    const links: FamilyTree["links"] = [];
    const seen = new Set<string>();
    const addLink = (source: number, target: number, kind: "parent" | "spouse") => {
      const key = `${source}-${target}-${kind}`;
      if (seen.has(key)) return;
      seen.add(key);
      links.push({ source, target, kind });
    };
    for (const p of compPersons) {
      for (const par of [p.father_id, p.mother_id]) {
        if (par != null && memberIds.has(par)) addLink(par, p.id, "parent");
      }
    }
    for (const [h, w] of compMarriages) {
      addLink(h, w, "spouse");
    }
    const layout = layoutTree({ nodes, links } as unknown as FamilyTree);

    const local = new Map<number, PlacedNode>();
    const placed: PlacedNode[] = layout.rows.flat().map((ln) => {
      const node: PlacedNode = {
        person: byId.get(ln.person.id)!,
        x: colX(ln.col),
        y: rowY(ln.row),
        w: COL_W,
        h: CHIP_H,
      };
      local.set(ln.person.id, node);
      return node;
    });

    const parent: number[] = [];
    for (const [parId, childId] of layout.parentEdges) {
      const P = local.get(parId);
      const C = local.get(childId);
      if (!P || !C) continue;
      parent.push(P.x + COL_W / 2, P.y + CHIP_H, C.x + COL_W / 2, C.y);
    }
    const spouse: number[] = [];
    for (const [a, b] of layout.spousePairs) {
      const A = local.get(a);
      const B = local.get(b);
      if (!A || !B) continue;
      const y = Math.max(A.y, B.y) + CHIP_H + 6;
      spouse.push(A.x + COL_W / 2, y, B.x + COL_W / 2, y);
    }
    pending.push({ nodes: placed, parent, spouse, w: layout.width, h: layout.height });
  }

  // Pack the components into a uniform grid (largest first for tidiness).
  pending.sort((a, b) => b.h - a.h || b.w - a.w);
  const maxW = Math.max(...pending.map((p) => p.w), 600);
  const maxH = Math.max(...pending.map((p) => p.h), 140);
  const cellW = maxW + GRID_GAP_X;
  const cellH = maxH + GRID_GAP_Y;
  const cols = Math.max(1, Math.ceil(Math.sqrt(pending.length * (cellH / cellW))));
  const rows = Math.ceil(pending.length / cols);

  const allNodes: PlacedNode[] = [];
  const posById = new Map<number, PlacedNode>();
  const parentEdges: number[] = [];
  const spouseEdges: number[] = [];

  pending.forEach((p, i) => {
    const gc = i % cols;
    const gr = Math.floor(i / cols);
    const ox = gc * cellW + (cellW - p.w) / 2;
    const oy = gr * cellH + CELL_PAD_TOP;
    for (const n of p.nodes) {
      const moved: PlacedNode = { ...n, x: n.x + ox, y: n.y + oy };
      allNodes.push(moved);
      posById.set(moved.person.id, moved);
    }
    for (let j = 0; j < p.parent.length; j += 4) {
      parentEdges.push(p.parent[j] + ox, p.parent[j + 1] + oy, p.parent[j + 2] + ox, p.parent[j + 3] + oy);
    }
    for (let j = 0; j < p.spouse.length; j += 4) {
      spouseEdges.push(p.spouse[j] + ox, p.spouse[j + 1] + oy, p.spouse[j + 2] + ox, p.spouse[j + 3] + oy);
    }
  });

  return {
    nodes: allNodes,
    posById,
    parentEdges,
    spouseEdges,
    width: cols * cellW - GRID_GAP_X,
    height: rows * cellH - GRID_GAP_Y,
    components: pending.length,
  };
}