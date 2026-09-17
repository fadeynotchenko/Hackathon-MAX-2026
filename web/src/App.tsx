import { Navigate, Route, Routes } from 'react-router-dom';

import { useAuth } from '@/auth/context';
import { AdminPage } from '@/pages/AdminPage';
import { GatePage } from '@/pages/GatePage';
import { HomePage } from '@/pages/HomePage';
import { ProfilePage } from '@/pages/ProfilePage';

export function App() {
  const { status, user } = useAuth();
  if (status !== 'ready' || !user) return <GatePage />;
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/admin" element={user.is_admin ? <AdminPage /> : <Navigate to="/" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
