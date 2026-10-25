import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
});

const TOKEN_STORAGE_KEY = 'fincomply_api_token';
export const USER_STORAGE_KEY = 'fincomply_user';

export const getApiToken = () => {
  if (typeof window === 'undefined') return '';
  return window.sessionStorage.getItem(TOKEN_STORAGE_KEY) || '';
};

export const setApiToken = (token) => {
  if (typeof window === 'undefined') return;
  const cleanToken = token.trim();
  if (cleanToken) {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, cleanToken);
  } else {
    window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  }
};

export const getStoredUser = () => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(USER_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
};

export const clearAuth = () => {
  window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  window.sessionStorage.removeItem(USER_STORAGE_KEY);
  window.sessionStorage.removeItem('fincomply_last_analysis');
};

// Attach JWT from session storage to every request automatically.
api.interceptors.request.use((config) => {
  const token = getApiToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Auth API ──────────────────────────────────────────────────────────────────

export const loginUser = async (username, password) => {
  try {
    const response = await api.post('/auth/login', { username, password });
    const data = response.data;
    // Persist token + user profile (including tenant_id for auto-fill)
    setApiToken(data.access_token);
    window.sessionStorage.setItem(USER_STORAGE_KEY, JSON.stringify({
      username: data.username,
      name: data.name,
      role: data.role,
      tenant_id: data.tenant_id || '',
    }));
    return data;
  } catch (error) {
    const detail = error.response?.data?.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Login failed. Check your credentials.', { cause: error });
  }
};

export const registerUser = async ({ name, email, username, password, tenant_id, tenant_name }) => {
  try {
    const response = await api.post('/auth/register', { name, email, username, password, tenant_id, tenant_name });
    return response.data;
  } catch (error) {
    const detail = error.response?.data?.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Registration failed. Please try again.', { cause: error });
  }
};

const formatDetailError = (detail) => {
  if (!detail) return null;
  if (Array.isArray(detail)) {
    return detail.map((e) => `${e.loc?.join('.') || 'error'}: ${e.msg}`).join(', ');
  }
  if (typeof detail === 'object') {
    if (detail.message || detail.detail) {
      return detail.message || detail.detail;
    }
    return JSON.stringify(detail);
  }
  return String(detail);
};

export const runAnalysis = async (formData) => {
  try {
    const response = await api.post('/analyze/upload', formData);
    return response.data;
  } catch (error) {
    if (error.response) {
      const errMsg = formatDetailError(error.response.data?.detail) || 'Failed to analyze data';
      throw new Error(errMsg, { cause: error });
    }
    throw new Error('Network error. Ensure the backend is running.', { cause: error });
  }
};

export const runAnalysisExisting = async (tenantId) => {
  try {
    const response = await api.post('/analyze', { tenant_id: tenantId.trim() });
    return response.data;
  } catch (error) {
    if (error.response) {
      const errMsg = formatDetailError(error.response.data?.detail) || 'Failed to analyze existing tenant';
      throw new Error(errMsg, { cause: error });
    }
    throw new Error('Network error. Ensure the backend is running.', { cause: error });
  }
};

// Remembers which run the dashboard is showing, so a page refresh can reload it.
const LAST_ANALYSIS_KEY = 'fincomply_last_analysis';

export const saveLastAnalysis = (tenantId, auditRunId) => {
  if (typeof window === 'undefined' || !tenantId) return;
  window.sessionStorage.setItem(LAST_ANALYSIS_KEY, JSON.stringify({ tenant_id: tenantId, audit_run_id: auditRunId || null }));
};

export const getLastAnalysis = () => {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(LAST_ANALYSIS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
};

export const clearLastAnalysis = () => {
  if (typeof window === 'undefined') return;
  window.sessionStorage.removeItem(LAST_ANALYSIS_KEY);
};

export const getDashboardData = async (tenantId, auditRunId) => {
  try {
    const response = await api.get(`/dashboard/${encodeURIComponent(tenantId)}`, {
      params: auditRunId ? { audit_run_id: auditRunId } : {},
    });
    return response.data;
  } catch (error) {
    const errMsg = formatDetailError(error.response?.data?.detail) || 'Failed to load dashboard';
    throw new Error(errMsg, { cause: error });
  }
};

export const downloadPdfReport = async (tenantId, auditRunId) => {
  try {
    const response = await api.get(`/report/pdf/${tenantId}`, {
      responseType: 'blob',
      params: auditRunId ? { audit_run_id: auditRunId } : {},
    });
    return response.data;
  } catch (error) {
    if (error.response) {
      const detail = error.response.data?.detail;
      throw new Error(detail || 'Failed to generate PDF.', { cause: error });
    }
    throw new Error('Network error. Ensure the backend is running.', { cause: error });
  }
};

export const getRules = async () => {
  try {
    const response = await api.get('/rules');
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Failed to fetch active rules', { cause: error });
    }
    throw new Error('Network error. Ensure the backend is running.', { cause: error });
  }
};

export const getProposedRules = async () => {
  try {
    const response = await api.get('/rules/proposed');
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Failed to fetch proposed rules', { cause: error });
    }
    throw new Error('Network error. Ensure the backend is running.', { cause: error });
  }
};

export const approveRule = async (proposalId) => {
  try {
    const response = await api.post(`/rules/approve/${proposalId}`);
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || `Failed to approve proposal ${proposalId}`, { cause: error });
    }
    throw new Error('Network error. Ensure the backend is running.', { cause: error });
  }
};

export const rejectRule = async (proposalId, reason = 'Rejected by reviewer') => {
  try {
    const response = await api.post(`/rules/reject/${proposalId}`, null, {
      params: { reason },
    });
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || `Failed to reject proposal ${proposalId}`, { cause: error });
    }
    throw new Error('Network error. Ensure the backend is running.', { cause: error });
  }
};
