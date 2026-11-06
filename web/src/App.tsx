import { Navigate, Route, Routes } from "react-router-dom";
import { useMock } from "./api";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/context";
import { AppShell } from "./layout/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { CasesPage } from "./pages/CasesPage";
import { UploadPage } from "./pages/UploadPage";
import { ExtractPage } from "./pages/ExtractPage";
import { ReportPage } from "./pages/ReportPage";
import { AskPage } from "./pages/AskPage";
import { AuditPage } from "./pages/AuditPage";
import { ModelsPage } from "./pages/ModelsPage";
import type { ReactNode } from "react";

function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  if (loading)
    return (
      <div role="status" style={{ padding: 24 }}>
        …
      </div>
    );
  if (!session) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <>
        {useMock ? (
          <div className="mock-banner" role="status">
            MOCK 数据 · 仅开发 / DEVELOPMENT ONLY
          </div>
        ) : null}
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/cases" replace />} />
            <Route path="cases" element={<CasesPage />} />
            <Route path="cases/new" element={<UploadPage />} />
            <Route path="cases/:id/extract" element={<ExtractPage />} />
            <Route path="cases/:id/report" element={<ReportPage />} />
            <Route path="cases/:id/ask" element={<AskPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="system/models" element={<ModelsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </>
    </AuthProvider>
  );
}
