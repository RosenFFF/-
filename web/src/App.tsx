import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { AppShell } from './layout/AppShell';
import { LoginPage } from './pages/LoginPage';
import { CasesPage } from './pages/CasesPage';
import { UploadPage } from './pages/UploadPage';
import { ExtractPage } from './pages/ExtractPage';
import { ReportPage } from './pages/ReportPage';
import { AskPage } from './pages/AskPage';
import { AuditPage } from './pages/AuditPage';
import { ModelsPage } from './pages/ModelsPage';
import type { ReactNode } from 'react';

function RequireAuth({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
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
    </AuthProvider>
  );
}
