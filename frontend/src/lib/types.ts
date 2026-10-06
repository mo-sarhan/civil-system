/** Shapes returned by the civil-registry API. */

export type Role = "admin" | "editor" | "viewer";

export interface User {
  id: number;
  username: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface LoginResponse extends TokenPair {
  user: User;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Person {
  id: number;
  national_id: string | null;
  national_id_masked: boolean;
  full_name: string;
  first_name: string | null;
  father_name: string | null;
  grandfather_name: string | null;
  family_name: string | null;
  gender: "M" | "F" | null;
  birth_date: string | null;
  death_date: string | null;
  birth_place: string | null;
  father_id: number | null;
  mother_id: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  merged_into_id: number | null;
}

export interface FieldError {
  field: string | null;
  message: string;
  type?: string;
}

/** FastAPI returns `detail` as a plain string for domain errors and as a list
 *  for request-validation errors; domain errors may also carry `errors`. */
export interface ApiErrorPayload {
  detail?: string | FieldError[];
  errors?: FieldError[];
}

export const ROLE_LABELS: Record<Role, string> = {
  admin: "مدير",
  editor: "محرر",
  viewer: "قارئ",
};

/* --- family structure ---------------------------------------------------- */

export interface ParentsResponse {
  person_id: number;
  father: Person | null;
  mother: Person | null;
}

export interface ChildrenResponse {
  person_id: number;
  as_father: Person[];
  as_mother: Person[];
  total: number;
}

export interface SiblingsResponse {
  person_id: number;
  full: Person[];
  half_paternal: Person[];
  half_maternal: Person[];
  total: number;
}

export interface SpouseEntry extends Person {
  marriage_id?: number;
  marriage_status?: string;
  marriage_date?: string | null;
}

export interface SpousesResponse {
  person_id: number;
  spouses: SpouseEntry[];
  total: number;
}

export interface Relative extends Person {
  relation: string;
  relation_code: string;
  generation_diff: number;
  path: number[];
}

export interface RelativesResponse {
  person_id: number;
  uncles_aunts: Relative[];
  cousins: Relative[];
  nephews_nieces: Relative[];
  in_laws: Relative[];
  grand_uncles: Relative[];
  grand_aunts: Relative[];
  summary: Record<string, number>;
}

export interface FamilySummary {
  person_id: number;
  children: number;
  siblings: number;
  spouses: number;
  descendants: number;
  ancestors: number;
  marriages: number;
}

/** A node in `GET /persons/{id}/tree`. `depth` is negative for ancestors. */
export interface TreeNode {
  id: number;
  full_name: string;
  gender: "M" | "F" | null;
  birth_date: string | null;
  death_date: string | null;
  birth_place: string | null;
  father_id: number | null;
  mother_id: number | null;
  depth: number;
  generation: string;
  children: number[];
  has_more_parents: boolean;
  has_more_children: boolean;
}

export type TreeLinkKind = "parent" | "spouse";

export interface TreeLink {
  source: number;
  target: number;
  kind: TreeLinkKind;
}

export interface Marriage {
  id: number;
  husband_id: number;
  wife_id: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
}

export interface FamilyTree {
  person_id: number;
  up: number;
  down: number;
  nodes: TreeNode[];
  links: TreeLink[];
  marriages: Marriage[];
  total_nodes: number;
  truncated: boolean;
}

/* --- marriages & duplicates ---------------------------------------------- */

export type MarriageStatus = "married" | "divorced" | "widowed" | "separated";

export interface Marriage {
  id: number;
  husband_id: number;
  wife_id: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
  husband_name: string | null;
  wife_name: string | null;
}

export interface DuplicatePerson {
  id: number;
  full_name: string;
  national_id: string | null;
  gender: "M" | "F" | null;
  birth_date: string | null;
  birth_place: string | null;
  father_id: number | null;
  mother_id: number | null;
  reasons?: string[];
  confidences?: number[];
  children?: number;
  spouses?: number;
}

export interface DuplicateGroup {
  key: string;
  reason: string;
  confidence: number;
  persons: DuplicatePerson[];
}

export interface DuplicatesResult {
  groups: DuplicateGroup[];
  total_groups: number;
  threshold: number;
}

export interface CompareField {
  field: string;
  a: string | number | null;
  b: string | number | null;
  same: boolean;
}

export interface CompareResult {
  a: DuplicatePerson;
  b: DuplicatePerson;
  fields: CompareField[];
  differences: number;
  name_similarity: number;
  recommendation: string;
}
