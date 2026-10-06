import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/context";
import { ROLE_LABELS, type Role } from "../lib/types";

interface NavItem {
  to: string;
  label: string;
  roles?: Role[];
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "السجل",
    items: [
      { to: "/", label: "لوحة المعلومات" },
      { to: "/persons", label: "الأشخاص" },
      { to: "/duplicates", label: "المكررات" },
      { to: "/marriages", label: "الزيجات" },
      { to: "/tree", label: "شجرة العائلة" },
      { to: "/relationships", label: "صلة القرابة" },
    ],
  },
  {
    section: "البيانات",
    items: [
      { to: "/imports", label: "رفع ملف", roles: ["admin", "editor"] },
      { to: "/exports", label: "التصدير" },
    ],
  },
  {
    section: "الإدارة",
    items: [
      { to: "/users", label: "المستخدمون", roles: ["admin"] },
      { to: "/audit", label: "سجل التدقيق", roles: ["admin"] },
    ],
  },
];

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const role = user?.role ?? "viewer";

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-e border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-5">
          <div className="text-base font-bold text-slate-900">السجل المدني</div>
          <div className="text-xs text-slate-500">شجرة العائلة</div>
        </div>

        <nav className="flex-1 overflow-y-auto py-4">
          {NAV.map((group) => {
            const items = group.items.filter(
              (item) => !item.roles || item.roles.includes(role),
            );
            if (items.length === 0) return null;
            return (
              <div key={group.section} className="mb-5">
                <div className="px-5 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {group.section}
                </div>
                {items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) =>
                      [
                        "block border-e-2 px-5 py-2 text-sm transition",
                        isActive
                          ? "border-slate-900 bg-slate-100 font-semibold text-slate-900"
                          : "border-transparent text-slate-600 hover:bg-slate-50 hover:text-slate-900",
                      ].join(" ")
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-slate-200 px-5 py-4">
          <div className="truncate text-sm font-medium text-slate-900">
            {user?.full_name || user?.username}
          </div>
          <div className="mb-3 text-xs text-slate-500">{ROLE_LABELS[role]}</div>
          <button
            type="button"
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="text-sm font-medium text-red-600 hover:text-red-700"
          >
            تسجيل الخروج
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
