import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../auth/context";
import { api, errorMessage } from "../lib/api";
import type { Page, Role, User } from "../lib/types";

const ROLE_LABELS: Record<string, string> = {
  admin: "مدير",
  editor: "محرر",
  viewer: "مشاهد",
};

const ROLE_ORDER: Role[] = ["admin", "editor", "viewer"];

interface CreateForm {
  username: string;
  full_name: string;
  password: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
}

interface EditState {
  role: Role;
  is_active: boolean;
}

export default function UsersPage() {
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = me?.role === "admin";

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<{ id: number; username: string } | null>(null);
  const [form, setForm] = useState<CreateForm>({
    username: "",
    full_name: "",
    password: "",
    role: "viewer",
    is_active: true,
    must_change_password: true,
  });
  const [editForm, setEditForm] = useState<EditState>({ role: "viewer", is_active: true });

  const { data, isPending, error } = useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const { data } = await api.get<Page<User>>("/users?page=1&page_size=100");
      return data;
    },
    enabled: isAdmin,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/users", form);
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setCreating(false);
      setForm({ username: "", full_name: "", password: "", role: "viewer", is_active: true, must_change_password: true });
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ user }: { user: number }) => {
      const { data } = await api.patch(`/users/${user}`, editForm);
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditing(null);
    },
  });

  const unlockMutation = useMutation({
    mutationFn: async (id: number) => (await api.post(`/users/${id}/unlock`)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const removeMutation = useMutation({
    mutationFn: async (id: number) => api.delete(`/users/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  if (!isAdmin) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white px-6 py-10 text-center text-sm text-slate-500">
        إدارة المستخدمين متاحة للمدير فقط.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">المستخدمون</h1>
          <p className="mt-1 text-sm text-slate-500">{data ? `${data.total.toLocaleString("ar-EG")} مستخدم` : " "}</p>
        </div>
        {!creating && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700"
          >
            إضافة مستخدم
          </button>
        )}
      </header>

      {(createMutation.isError || updateMutation.isError || removeMutation.isError) && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage(createMutation.error ?? updateMutation.error ?? removeMutation.error)}
        </div>
      )}

      {creating && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
          className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900">مستخدم جديد</h2>
            <button type="button" onClick={() => setCreating(false)} className="text-sm text-slate-500 underline hover:text-slate-800">
              إلغاء
            </button>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">اسم المستخدم *</span>
              <input required minLength={3} pattern="[A-Za-z0-9._-]+" className="field-input ltr" value={form.username} onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">الاسم الكامل</span>
              <input className="field-input" value={form.full_name} onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">كلمة المرور *</span>
              <input required className="field-input ltr" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))} />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-slate-700">الدور</span>
              <select className="field-input" value={form.role} onChange={(e) => setForm((p) => ({ ...p, role: e.target.value as Role }))}>
                {ROLE_ORDER.map((role) => (
                  <option key={role} value={role}>{ROLE_LABELS[role]}</option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
              <input type="checkbox" checked={form.is_active} onChange={(e) => setForm((p) => ({ ...p, is_active: e.target.checked }))} className="h-4 w-4" />
              مفعّل
            </label>
            <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
              <input type="checkbox" checked={form.must_change_password} onChange={(e) => setForm((p) => ({ ...p, must_change_password: e.target.checked }))} className="h-4 w-4" />
              يغيّر كلمة المرور عند أول دخول
            </label>
          </div>
          <div className="mt-5 flex gap-3">
            <button type="submit" disabled={createMutation.isPending} className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50">
              {createMutation.isPending ? "جارٍ الحفظ…" : "إنشاء المستخدم"}
            </button>
            <button type="button" onClick={() => setCreating(false)} className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50">
              إلغاء
            </button>
          </div>
        </form>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 text-start font-semibold">اسم المستخدم</th>
              <th className="px-4 py-3 text-start font-semibold">الاسم الكامل</th>
              <th className="px-4 py-3 text-start font-semibold">الدور</th>
              <th className="px-4 py-3 text-start font-semibold">الحالة</th>
              <th className="ltr px-4 py-3 text-start font-semibold">آخر دخول</th>
              <th className="px-4 py-3 text-end font-semibold">إجراءات</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isPending && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-slate-400">جارٍ التحميل…</td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-red-600">{errorMessage(error)}</td>
              </tr>
            )}
            {data?.items.map((user) => (
              <tr key={user.id} className="hover:bg-slate-50">
                <td className="ltr px-4 py-3 text-slate-800">
                  {user.username}
                  {user.id === me?.id && <span className="ms-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">أنت</span>}
                </td>
                <td className="px-4 py-3 text-slate-700">{user.full_name ?? "—"}</td>
                <td className="px-4 py-3">
                  <RoleBadge role={user.role} />
                  {user.must_change_password && <span className="ms-2 text-[10px] text-amber-600">يجب تغيير كلمة المرور</span>}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-xs ${
                      user.is_active
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "border-red-200 bg-red-50 text-red-600"
                    }`}
                  >
                    {user.is_active ? "مفعّل" : "معطّل"}
                  </span>
                </td>
                <td className="ltr px-4 py-3 text-slate-500">{formatDate(user.last_login_at)}</td>
                <td className="px-4 py-3 text-end">
                  {editing?.id === user.id ? (
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        updateMutation.mutate({ user: user.id });
                      }}
                      className="flex items-center justify-end gap-2"
                    >
                      <select className="field-input w-28" value={editForm.role} onChange={(e) => setEditForm((p) => ({ ...p, role: e.target.value as Role }))}>
                        {ROLE_ORDER.map((role) => (
                          <option key={role} value={role}>{ROLE_LABELS[role]}</option>
                        ))}
                      </select>
                      <select className="field-input w-28" value={String(editForm.is_active)} onChange={(e) => setEditForm((p) => ({ ...p, is_active: e.target.value === "true" }))}>
                        <option value="true">مفعّل</option>
                        <option value="false">معطّل</option>
                      </select>
                      <button type="submit" className="text-sm text-emerald-700 underline hover:text-emerald-900">حفظ</button>
                      <button type="button" onClick={() => setEditing(null)} className="text-sm text-slate-500 underline hover:text-slate-800">إلغاء</button>
                    </form>
                  ) : (
                    <>
                      <button
                        type="button"
                        onClick={() => {
                          setEditing({ id: user.id, username: user.username });
                          setEditForm({ role: user.role as Role, is_active: user.is_active });
                        }}
                        className="text-sm text-slate-600 underline hover:text-slate-900"
                      >
                        تعديل
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`فك قفل حساب ${user.username}؟`)) unlockMutation.mutate(user.id);
                        }}
                        className="ms-3 text-sm text-amber-700 underline hover:text-amber-800"
                      >
                        فك قفل
                      </button>
                      {user.id !== me?.id && (
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm(`حذف المستخدم ${user.username} نهائياً؟`)) removeMutation.mutate(user.id);
                          }}
                          className="ms-3 text-sm text-red-600 underline hover:text-red-700"
                        >
                          حذف
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RoleBadge({ role }: { role: string }) {
  const tones: Record<string, string> = {
    admin: "border-purple-200 bg-purple-50 text-purple-700",
    editor: "border-sky-200 bg-sky-50 text-sky-700",
    viewer: "border-slate-200 bg-slate-100 text-slate-600",
  };
  return <span className={`rounded-full border px-2.5 py-0.5 text-xs ${tones[role] ?? tones.viewer}`}>{ROLE_LABELS[role] ?? role}</span>;
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "short" });
}