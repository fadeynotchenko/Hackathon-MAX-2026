import { useEffect, useRef } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';

import { useAuth } from '@/auth/context';
import { startRoute } from '@/lib/startRoute';
import { getStartParam } from '@/max/webapp';
import { AdminPage } from '@/pages/AdminPage';
import { ArchivePage } from '@/pages/archive/ArchivePage';
import { ClientPage } from '@/pages/create/ClientPage';
import { CreatePage } from '@/pages/create/CreatePage';
import { TemplatePage } from '@/pages/create/TemplatePage';
import { DocumentPage } from '@/pages/document/DocumentPage';
import { ExportPage } from '@/pages/document/ExportPage';
import { FillPage } from '@/pages/document/FillPage';
import { ReviewPage } from '@/pages/document/ReviewPage';
import { SentPage } from '@/pages/document/SentPage';
import { GatePage } from '@/pages/GatePage';
import { CounterpartiesPage } from '@/pages/profile/CounterpartiesPage';
import { CounterpartyPage } from '@/pages/profile/CounterpartyPage';
import { OrganizationPage } from '@/pages/profile/OrganizationPage';
import { OrganizationsPage } from '@/pages/profile/OrganizationsPage';
import { ProfilePage } from '@/pages/profile/ProfilePage';

function StartRedirect() {
  const navigate = useNavigate();
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const route = startRoute(getStartParam());
    if (route) void navigate(route, { replace: true });
  }, [navigate]);
  return null;
}

export function App() {
  const { status, user } = useAuth();
  if (status !== 'ready' || !user) return <GatePage />;
  return (
    <>
      <StartRedirect />
      <Routes>
        <Route path="/" element={<Navigate to="/create" replace />} />
        <Route path="/create" element={<CreatePage />} />
        <Route path="/create/:templateId" element={<TemplatePage />} />
        <Route path="/create/:templateId/client" element={<ClientPage />} />
        <Route path="/documents/:documentId" element={<DocumentPage />} />
        <Route path="/documents/:documentId/fill" element={<FillPage />} />
        <Route path="/documents/:documentId/review" element={<ReviewPage />} />
        <Route path="/documents/:documentId/export" element={<ExportPage />} />
        <Route path="/documents/:documentId/sent" element={<SentPage />} />
        <Route path="/archive" element={<ArchivePage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/profile/organizations" element={<OrganizationsPage />} />
        <Route path="/profile/organizations/new" element={<OrganizationPage />} />
        <Route path="/profile/organizations/:organizationId" element={<OrganizationPage />} />
        {/* Старые ссылки из бота и закладок вели на единственную «мою организацию». */}
        <Route path="/profile/company" element={<Navigate to="/profile/organizations" replace />} />
        <Route path="/profile/counterparties" element={<CounterpartiesPage />} />
        <Route path="/profile/counterparties/new" element={<CounterpartyPage />} />
        <Route path="/profile/counterparties/:counterpartyId" element={<CounterpartyPage />} />
        <Route
          path="/admin"
          element={user.is_admin ? <AdminPage /> : <Navigate to="/profile" replace />}
        />
        <Route path="*" element={<Navigate to="/create" replace />} />
      </Routes>
    </>
  );
}
