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
