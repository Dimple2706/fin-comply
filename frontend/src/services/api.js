import axios from 'axios';

// In development, Vite proxy forwards /analyze and /report to the backend.
// In production, set VITE_API_BASE_URL to the actual backend URL.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const api = axios.create({
  baseURL: BASE_URL,
});

// Attach RBAC auth token to outgoing requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('fincomply_auth_token') || 'admin:admin_operator';
  config.headers['Authorization'] = `Bearer ${token}`;
  return config;
});

export const runAnalysis = async (formData) => {
  try {
    const response = await api.post('/analyze/upload', formData);
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Failed to analyze data');
    }
    throw new Error('Network error. Ensure the backend is running.');
  }
};

export const runAnalysisExisting = async (tenantId) => {
  try {
    const response = await api.post('/analyze', { tenant_id: tenantId.trim() });
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Failed to analyze existing tenant');
    }
    throw new Error('Network error. Ensure the backend is running.');
  }
};

export const downloadPdfReport = async (tenantId) => {
  try {
    const response = await api.get(`/report/pdf/${tenantId}`, {
      responseType: 'blob',
    });
    return response.data;
  } catch (error) {
    if (error.response) {
      const detail = error.response.data?.detail;
      throw new Error(detail || 'Failed to generate PDF.');
    }
    throw new Error('Network error. Ensure the backend is running.');
  }
};

export const getRules = async () => {
  try {
    const response = await api.get('/rules');
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Failed to fetch active rules');
    }
    throw new Error('Network error. Ensure the backend is running.');
  }
};

export const getProposedRules = async () => {
  try {
    const response = await api.get('/rules/proposed');
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Failed to fetch proposed rules');
    }
    throw new Error('Network error. Ensure the backend is running.');
  }
};

export const approveRule = async (proposalId) => {
  try {
    const response = await api.post(`/rules/approve/${proposalId}`);
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || `Failed to approve proposal ${proposalId}`);
    }
    throw new Error('Network error. Ensure the backend is running.');
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
      throw new Error(error.response.data.detail || `Failed to reject proposal ${proposalId}`);
    }
    throw new Error('Network error. Ensure the backend is running.');
  }
};

