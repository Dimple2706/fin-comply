import { BrowserRouter as Router, Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import AuthPage from './pages/AuthPage';
import Onboarding from './pages/Onboarding';
import Dashboard from './pages/Dashboard';
import {
  getApiToken, getStoredUser, clearAuth,
  saveLastAnalysis, getLastAnalysis, clearLastAnalysis, getDashboardData,
} from './services/api';

function AppContent() {
  // Auth state — read from session storage on first render so refresh keeps you logged in
  const [user, setUser] = useState(() => getStoredUser());
  const [token, setToken] = useState(() => getApiToken());
  const [analysisData, setAnalysisData] = useState(null);
  const navigate = useNavigate();

  const isAuthenticated = !!(token && user);

  // After a page refresh the analysis is gone from memory; reload the run the
  // dashboard was showing instead of bouncing the user back to the upload page.
  const [restoring, setRestoring] = useState(() => !!(getApiToken() && getStoredUser() && getLastAnalysis()));

  useEffect(() => {
    if (!restoring) return;
    const last = getLastAnalysis();
    let cancelled = false;
    getDashboardData(last.tenant_id, last.audit_run_id)
      .then((data) => { if (!cancelled) setAnalysisData(data); })
      .catch(() => { clearLastAnalysis(); })
      .finally(() => { if (!cancelled) setRestoring(false); });
    return () => { cancelled = true; };
  }, [restoring]);

  const handleLoginSuccess = (data) => {
    // data = { access_token, username, name, role }
    setToken(data.access_token);
    setUser({ username: data.username, name: data.name, role: data.role });
    navigate('/onboarding');
  };

  const handleAnalysisComplete = (data) => {
    setAnalysisData(data);
    saveLastAnalysis(data?.tenant_id, data?.audit_run_id);
    navigate('/dashboard');
  };

  const handleReset = () => {
    setAnalysisData(null);
    clearLastAnalysis();
    navigate('/onboarding');
  };

  const handleLogout = () => {
    clearAuth();
    setToken('');
    setUser(null);
    setAnalysisData(null);
    navigate('/');
  };

  return (
    <AnimatePresence mode="wait">
      <Routes>
        {/* ── Public: Auth landing (login / register) ── */}
        <Route
          path="/"
          element={
            isAuthenticated
              ? <Navigate to="/onboarding" replace />
              : <AuthPage onLoginSuccess={handleLoginSuccess} />
          }
        />

        {/* ── Protected: CSV upload / analysis ── */}
        <Route
          path="/onboarding"
          element={
            isAuthenticated
              ? <Onboarding
                  onComplete={handleAnalysisComplete}
                  user={user}
                  onLogout={handleLogout}
                />
              : <Navigate to="/" replace />
          }
        />

        {/* ── Protected: Results dashboard ── */}
        <Route
          path="/dashboard"
          element={
            isAuthenticated ? (
              analysisData
                ? <Dashboard data={analysisData} onReset={handleReset} user={user} onLogout={handleLogout} />
                : restoring
                  ? <div className="min-h-screen flex items-center justify-center text-sm opacity-70">Loading your report...</div>
                  : <Navigate to="/onboarding" replace />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

        {/* ── Fallback ── */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}
