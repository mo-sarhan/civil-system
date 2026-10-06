import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./context";
import { api, errorMessage } from "../lib/api";

/** Login plus the forced password change the API asks for on first sign-in. */
export default function LoginPage() {
  const { login, user, reload } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const needsPasswordChange = Boolean(user?.must_change_password);

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const signedIn = await login(username.trim(), password);
      if (!signedIn.must_change_password) navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePasswordChange(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (newPassword !== confirmPassword) {
      setError("كلمتا المرور الجديدتان غير متطابقتين");
      return;
    }
    setBusy(true);
    try {
      await api.post("/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      await reload();
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
      <div className="w-full max-w-md rounded-xl bg-white p-8 shadow-sm ring-1 ring-slate-200">
        <h1 className="mb-1 text-center text-2xl font-bold text-slate-900">
          نظام السجل المدني
        </h1>
        <p className="mb-6 text-center text-sm text-slate-500">
          {needsPasswordChange ? "يجب تغيير كلمة المرور قبل المتابعة" : "تسجيل الدخول إلى الحساب"}
        </p>

        {error && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </div>
        )}

        {!needsPasswordChange ? (
          <form onSubmit={handleLogin} className="space-y-4">
            <Field label="اسم المستخدم">
              <input
                autoFocus
                required
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="field-input"
              />
            </Field>
            <Field label="كلمة المرور">
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="field-input"
              />
            </Field>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-slate-900 py-2.5 font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50"
            >
              {busy ? "جارٍ التحقق…" : "دخول"}
            </button>
          </form>
        ) : (
          <form onSubmit={handlePasswordChange} className="space-y-4">
            <Field label="كلمة المرور الحالية">
              <input
                type="password"
                required
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="field-input"
              />
            </Field>
            <Field label="كلمة المرور الجديدة">
              <input
                type="password"
                required
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="field-input"
              />
            </Field>
            <Field label="تأكيد كلمة المرور الجديدة">
              <input
                type="password"
                required
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="field-input"
              />
            </Field>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-slate-900 py-2.5 font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50"
            >
              {busy ? "جارٍ الحفظ…" : "حفظ كلمة المرور"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}
