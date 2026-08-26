import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000',
});

// Configure simple token-based headers
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token') || 'secure_test_admin_token_2026';
  config.headers.Authorization = `Bearer ${token}`;
  return config;
});

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

export const downloadPdfReport = async (tenantId) => {
  try {
    const response = await api.get(`/report/pdf/${tenantId}`, {
      responseType: 'blob',
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
