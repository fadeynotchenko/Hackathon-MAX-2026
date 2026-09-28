import { useMemo, useState } from 'react';
import { Navigate, Route, Routes, useLocation, type Location } from 'react-router-dom';

import { useAuth } from '@/auth/context';
import { TAB_PATHS } from '@/components/tabs';
import { ScreenContext, useScreenStack, useScrollMemory } from '@/lib/screenMemory';
import { startRoute } from '@/lib/startRoute';
import { getStartParam } from '@/max/webapp';
import { AdminPage } from '@/pages/admin/AdminPage';
import { ArchivePage } from '@/pages/archive/ArchivePage';
import { CreatePage } from '@/pages/create/CreatePage';
import { TemplatePage } from '@/pages/create/TemplatePage';
import { ClientPickPage } from '@/pages/document/ClientPickPage';
import { DocumentPage } from '@/pages/document/DocumentPage';
import { ExportPage } from '@/pages/document/ExportPage';
import { FillPage } from '@/pages/document/FillPage';
import { ImportPage } from '@/pages/document/ImportPage';
import { PhotoFillPage } from '@/pages/document/PhotoFillPage';
import { ReviewPage } from '@/pages/document/ReviewPage';
import { SellerPickPage } from '@/pages/document/SellerPickPage';
import { SentPage } from '@/pages/document/SentPage';
import { TextFillPage } from '@/pages/document/TextFillPage';
import { VoiceFillPage } from '@/pages/document/VoiceFillPage';
import { GatePage } from '@/pages/GatePage';
import { CounterpartiesPage } from '@/pages/profile/CounterpartiesPage';
import { CounterpartyPage } from '@/pages/profile/CounterpartyPage';
import { OrganizationPage } from '@/pages/profile/OrganizationPage';
import { OrganizationsPage } from '@/pages/profile/OrganizationsPage';
import { ProfilePage } from '@/pages/profile/ProfilePage';
import { TemplateEditorPage } from '@/pages/templates/TemplateEditorPage';
import { TemplateSamplePage } from '@/pages/templates/TemplateSamplePage';

// Экран стека: скрыт, пока поверх него открыт другой, и помнит, сколько раз
// на него возвращались.
function StackedScreen({
  location,
  active,
  isAdmin,
}: {
  location: Location;
  active: boolean;
  isAdmin: boolean;
}) {
  const [returns, setReturns] = useState(0);
  const [wasActive, setWasActive] = useState(active);
  if (wasActive !== active) {
    setWasActive(active);
    if (active) setReturns((n) => n + 1);
  }
  const activity = useMemo(() => ({ active, returns }), [active, returns]);
  return (
    <ScreenContext.Provider value={activity}>
      <div style={{ display: active ? 'contents' : 'none' }}>
        <AppRoutes location={location} isAdmin={isAdmin} />
      </div>
    </ScreenContext.Provider>
  );
}

export function App() {
  const { status, user } = useAuth();
  const location = useLocation();
  const stack = useScreenStack();
  useScrollMemory(TAB_PATHS);
  if (status !== 'ready' || !user) return <GatePage />;
  return (
    <>
      {stack.map((entry) => (
        <StackedScreen
          key={entry.key}
          location={entry}
          active={entry.key === location.key}
          isAdmin={user.is_admin}
        />
      ))}
    </>
  );
}

function AppRoutes({ location, isAdmin }: { location: Location; isAdmin: boolean }) {
  return (
    <Routes location={location}>
      {/* Мини-апп открывается на корне; кнопка бота или ссылка ?startapp= ведут
          сразу на свой экран. Отдельный редирект после старта проигрывал гонку
          этому же маршруту: его переход на каталог срабатывал следом. */}
      <Route
        path="/"
        element={<Navigate to={startRoute(getStartParam()) ?? '/create'} replace />}
      />
      <Route path="/create" element={<CreatePage />} />
      <Route path="/create/:templateId" element={<TemplatePage />} />
      {/* Экрана «Для кого документ?» больше нет: «Заполнить» сразу открывает форму. */}
      <Route
        path="/create/:templateId/client"
        element={<Navigate to=".." relative="path" replace />}
      />
      <Route path="/templates/new" element={<TemplateEditorPage />} />
      <Route path="/templates/upload" element={<TemplateSamplePage />} />
      <Route path="/templates/:templateId/edit" element={<TemplateEditorPage />} />
      <Route path="/documents/import" element={<ImportPage />} />
      <Route path="/documents/:documentId" element={<DocumentPage />} />
      <Route path="/documents/:documentId/fill" element={<FillPage />} />
      <Route path="/documents/:documentId/fill/photo" element={<PhotoFillPage />} />
      <Route path="/documents/:documentId/fill/voice" element={<VoiceFillPage />} />
      <Route path="/documents/:documentId/fill/text" element={<TextFillPage />} />
      <Route path="/documents/:documentId/fill/client" element={<ClientPickPage />} />
      <Route path="/documents/:documentId/fill/seller" element={<SellerPickPage />} />
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
      <Route path="/admin" element={isAdmin ? <AdminPage /> : <Navigate to="/profile" replace />} />
      <Route path="*" element={<Navigate to="/create" replace />} />
    </Routes>
  );
}
