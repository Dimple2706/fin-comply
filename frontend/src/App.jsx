import { BrowserRouter as Router, Routes, Route, useNavigate, Navigate } from 'react-router-dom';
import { useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import AuthPage from './pages/AuthPage';
import Onboarding from './pages/Onboarding';
import Dashboard from './pages/Dashboard';
import TaskAssessment from './pages/TaskAssessment';
import { getApiToken, getStoredUser, clearAuth } from './services/api';

function AppContent() {
  // Auth state — read from session storage on first render so refresh keeps you logged in
  const [user, setUser] = useState(() => getStoredUser());
  const [token, setToken] = useState(() => getApiToken());
  const [analysisData, setAnalysisData] = useState(null);
  const navigate = useNavigate();

  const isAuthenticated = !!(token && user);

  const handleLoginSuccess = (data) => {
    // data = { access_token, username, name, role }
    setToken(data.access_token);
    setUser({ username: data.username, name: data.name, role: data.role });
    navigate('/onboarding');
  };

  const handleAnalysisComplete = (data) => {
    setAnalysisData(data);
    navigate('/dashboard');
  };

  const handleReset = () => {
    setAnalysisData(null);
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
                : <Navigate to="/onboarding" replace />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/task-assessment"
          element={
            isAuthenticated ? (
             analysisData ? (
          <TaskAssessment
          data={analysisData}
          onBack={() => navigate('/dashboard')}
        />
        ) : (
          <Navigate to="/onboarding" replace />
        )
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
