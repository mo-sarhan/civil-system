import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./context";

/** Blocks the app until a session exists, then sends the user to login. */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        جارٍ التحقق من الجلسة…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  return <>{children}</>;
}
