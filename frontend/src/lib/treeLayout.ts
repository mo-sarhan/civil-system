import type { FamilyTree, TreeNode } from "./types";

/**
 * Turn the flat `nodes`/`links` payload from `GET /persons/{id}/tree` into a
 * rooted, couple-aware layout.
 *
 * Family data is a DAG (everyone has two parents), so we anchor on the subject
 * and treat both its ancestors and its descendants as branches of one tree.
 * A couple is a unit of one or two adjacent columns; every unit is centered
 * over its branches with the classic bottom-up width / top-down centered
 * placement. Spouses therefore always sit side by side.
 */

export const COL_W = 152; // px per person column
export const COL_GAP = 26;
export const ROW_H = 92; // chip height + room for the edges
export const ROW_GAP = 52;

export interface LayoutNode {
  person: TreeNode;
  row: number; // increasing = lower on screen
  col: number; // left edge in column units
}

export interface Layout {
  rows: LayoutNode[][];
  parentEdges: [number, number][];
  spousePairs: [number, number][];
  width: number; // px
  height: number; // px
}

interface Unit {
  members: number[];
  children: Unit[];
  width: number;
  left: number;
}

export function layoutTree(tree: FamilyTree): Layout {
  const byId = new Map<number, TreeNode>();
  for (const n of tree.nodes) byId.set(n.id, n);
  const depthOf = new Map<number, number>();
  for (const n of tree.nodes) depthOf.set(n.id, n.depth);

  // 1. Couples: marry two people at the same depth, everything else is solo.
  const spouseOf = new Map<number, number>();
  for (const l of tree.links) {
    if (l.kind === "spouse" && depthOf.get(l.source) === depthOf.get(l.target)) {
      spouseOf.set(l.source, l.target);
      spouseOf.set(l.target, l.source);
    }
  }
  const coupleOfPerson = new Map<number, Unit>();
  const coupleFor = (ids: number[]): Unit => {
    const unit = { members: ids, children: [], width: 0, left: 0 };
    for (const id of ids) coupleOfPerson.set(id, unit);
    return unit;
  };
  for (const n of tree.nodes) {
    if (coupleOfPerson.has(n.id)) continue;
    const partner = spouseOf.get(n.id);
    if (partner !== undefined && !coupleOfPerson.has(partner)) {
      coupleFor([n.id, partner].sort((a, b) => a - b));
    } else {
      coupleFor([n.id]);
    }
  }

  // 2. Descendants of a couple (next generation below it).
  const descendants = new Map<Unit, Set<Unit>>();
  const childLinks = new Map<Unit, Set<number>>();
  for (const l of tree.links) {
    if (l.kind !== "parent") continue;
    const parent = coupleOfPerson.get(l.source);
    const child = coupleOfPerson.get(l.target);
    if (!parent || !child || parent === child) continue;
    if (!childLinks.has(parent)) childLinks.set(parent, new Set());
    childLinks.get(parent)!.add(l.target);
  }
  for (const [parent, childIds] of childLinks) {
    const seen = new Set<Unit>();
    for (const id of childIds) {
      const c = coupleOfPerson.get(id);
      if (c && !seen.has(c)) seen.add(c);
    }
    descendants.set(parent, seen);
  }

  // 3. Ancestor couple of a couple (the generation directly above). Choose the
  //    husband's couple first so the chain stays deterministic when parents
  //    are not married to each other.
  const ancestorOf = (unit: Unit): Unit | null => {
    const pick = (list: Array<number | null | undefined>) => {
      for (const id of list) {
        if (id != null) {
          const c = coupleOfPerson.get(id);
          if (c && c !== unit) return c;
        }
      }
      return null;
    };
    const members = [...unit.members].sort((a, b) => a - b);
    for (const id of members) {
      const p = byId.get(id);
      const chosen = pick([p?.father_id, p?.mother_id]);
      if (chosen) return chosen;
    }
    return null;
  };

  // 4. Assemble one tree rooted at the subject, walking both directions.
  const subject = tree.nodes.find((n) => n.depth === 0);
  if (!subject) return empty();
  const root = coupleOfPerson.get(subject.id);
  if (!root) return empty();

  // Breadth-first spanning tree from the subject over undirected adjacency
  // (children below, the ancestor couple above). BFS gives every couple a
  // single layout parent, so the tree is acyclic even though the raw graph is
  // a DAG, and the centered placement stays well-defined.
  {
    const visited = new Set<Unit>([root]);
    const queue: Unit[] = [root];
    while (queue.length > 0) {
      const unit = queue.shift()!;
      const neighbors = new Set<Unit>();
      for (const c of descendants.get(unit) ?? []) neighbors.add(c);
      const ancestor = ancestorOf(unit);
      if (ancestor) neighbors.add(ancestor);
      for (const branch of neighbors) {
        if (visited.has(branch)) continue;
        visited.add(branch);
        unit.children.push(branch);
        queue.push(branch);
      }
    }
  }

  // 5. Bottom-up widths, then centered top-down placement.
  const computeWidth = (unit: Unit): number => {
    const childW = unit.children.reduce((acc, c) => acc + computeWidth(c) + COL_GAP, 0);
    unit.width = Math.max(unit.members.length, childW > 0 ? childW - COL_GAP : 0);
    return unit.width;
  };
  computeWidth(root);

  const place = (unit: Unit, center: number | null, left?: number) => {
    if (center != null) {
      unit.left = center - unit.members.length / 2;
    } else {
      unit.left = left ?? 0;
    }
    const unitCenter = unit.left + unit.members.length / 2;
    if (unit.children.length > 0) {
      const block = unit.children.reduce((acc, c) => acc + c.width, 0) + COL_GAP * (unit.children.length - 1);
      let cursor = unitCenter - block / 2;
      for (const c of unit.children) {
        place(c, null, cursor);
        cursor += c.width + COL_GAP;
      }
    }
  };
  place(root, 0);

  // 6. Derive per-person rows from depth so ancestors sit above the subject.
  const placedIds = new Set<number>();
  const visit = (unit: Unit): void => {
    for (const m of unit.members) placedIds.add(m);
    for (const c of unit.children) visit(c);
  };
  visit(root);
  const minDepth = Math.min(...tree.nodes.filter((n) => placedIds.has(n.id)).map((n) => n.depth));
  const rowsMap = new Map<number, LayoutNode[]>();
  const note = (unit: Unit) => {
    for (let i = 0; i < unit.members.length; i++) {
      const id = unit.members[i];
      const person = byId.get(id);
      if (!person) continue;
      const row = depthOf.get(id)! - minDepth;
      const node: LayoutNode = { person, row, col: unit.left + i };
      if (!rowsMap.has(row)) rowsMap.set(row, []);
      rowsMap.get(row)!.push(node);
    }
    for (const c of unit.children) note(c);
  };
  note(root);

  const rows = [...rowsMap.keys()]
    .sort((a, b) => a - b)
    .map((row) => rowsMap.get(row)!.sort((a, b) => a.col - b.col));

  // Normalize so the leftmost column is 0 and the subject stays centered.
  const minCol = Math.min(...rows.flat().map((n) => n.col), 0);
  for (const r of rows) for (const n of r) n.col -= minCol;

  const parentEdges: [number, number][] = [];
  const spousePairs: [number, number][] = [];
  for (const l of tree.links) {
    if (l.kind === "parent") parentEdges.push([l.source, l.target]);
    else if (l.kind === "spouse") spousePairs.push([l.source, l.target]);
  }

  const maxCol = Math.max(...rows.flat().map((n) => n.col), 0);
  return {
    rows,
    parentEdges,
    spousePairs,
    width: Math.max(maxCol * COL_W + (maxCol - 1) * COL_GAP + COL_W, 640),
    height: rows.length * ROW_H + (rows.length - 1) * ROW_GAP,
  };
}

function empty(): Layout {
  return { rows: [], parentEdges: [], spousePairs: [], width: 0, height: 0 };
}