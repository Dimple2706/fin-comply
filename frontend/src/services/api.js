import axios from 'axios';

// In development, Vite proxy forwards /analyze and /report to the backend.
// In production, set VITE_API_BASE_URL to the actual backend URL.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const api = axios.create({
  baseURL: BASE_URL,
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
