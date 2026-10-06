import { Navigate, Route, Routes } from "react-router-dom";
import LoginPage from "./auth/LoginPage";
import RequireAuth from "./auth/RequireAuth";
import AppShell from "./layout/AppShell";
import DashboardPage from "./pages/DashboardPage";
import PersonsPage from "./pages/PersonsPage";
import PlaceholderPage from "./pages/PlaceholderPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="persons" element={<PersonsPage />} />
        <Route path="persons/:personId" element={<PlaceholderPage title="ملف الشخص" />} />
        <Route path="tree" element={<PlaceholderPage title="شجرة العائلة" />} />
        <Route path="duplicates" element={<PlaceholderPage title="المكررات" />} />
        <Route path="marriages" element={<PlaceholderPage title="الزيجات" />} />
        <Route path="imports" element={<PlaceholderPage title="رفع ملفات" />} />
        <Route path="exports" element={<PlaceholderPage title="التصدير" />} />
        <Route path="users" element={<PlaceholderPage title="المستخدمون" />} />
        <Route path="audit" element={<PlaceholderPage title="سجل التدقيق" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
