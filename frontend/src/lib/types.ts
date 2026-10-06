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

/* --- users, audit, exports ---------------------------------------------- */

export interface AuditEntry {
  id: number;
  user_id: number | null;
  username: string | null;
  action: string;
  entity: string | null;
  entity_id: number | null;
  details: Record<string, unknown> | null;
  ip: string | null;
  created_at: string | null;
}

export interface AuditActions {
  actions: string[];
  entities: string[];
}

export interface AuditSummary {
  by_action: { action: string; count: number }[];
  top_users: { username: string; count: number }[];
  latest: string | null;
  total: number;
}

/* --- imports ------------------------------------------------------------ */

export type ImportStatus =
  | "pending"
  | "validating"
  | "ready"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface ImportFieldDef {
  key: string;
  label: string;
  required: boolean;
  aliases?: string[];
  available?: boolean;
}

export interface ImportError {
  row: number;
  field: string;
  value: string | null;
  message: string;
  severity: string;
}

export interface ImportPreview {
  job_id: number;
  filename: string;
  headers: string[];
  rows: (string | null)[][];
  total_rows: number;
  suggested_mapping: Record<string, number>;
  fields: ImportFieldDef[];
  linking_modes: Record<string, string>;
}

export interface ImportJob {
  id: number;
  filename: string;
  file_type: string;
  status: string;
  total_rows: number;
  processed_rows: number;
  success_rows: number;
  failed_rows: number;
  created_rows: number;
  updated_rows: number;
  progress: number;
  linking_mode: string | null;
  column_mapping: Record<string, number> | null;
  message: string | null;
  created_by: number;
  created_at: string | null;
  committed_at: string | null;
  error_report?: ImportError[];
  warnings?: unknown[];
}

export interface ImportValidationReport {
  job_id: number;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  errors_count: number;
  warnings_count: number;
  errors: ImportError[];
  errors_truncated: boolean;
  linking_mode: string;
  can_commit: boolean;
}

export interface ImportFieldsResponse {
  fields: ImportFieldDef[];
  linking_modes: { key: string; label: string }[];
  max_rows: number;
  chunk_size: number;
}

export interface MappingTemplate {
  id: number;
  name: string;
  description: string | null;
  mapping: Record<string, number>;
  linking_mode: string;
  is_shared: boolean;
  created_by: number;
  created_at: string | null;
}
