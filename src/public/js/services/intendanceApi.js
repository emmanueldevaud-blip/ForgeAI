import { ApiClient } from './api.js';

const api = new ApiClient('/intendance/expenses');

export const listExpenses = (params = {}) => api.get(`?${new URLSearchParams(params)}`);
export const listSites = () => api.get('/sites');
export const assignSites = (ids, site_id) => api.post('/sites/bulk', { ids, site_id });
export const analyzeImport = (file) => {
  const form = new FormData(); form.append('file', file);
  return api.post('/imports', form);
};
export const validateImport = (id) => api.post(`/imports/${id}/validate`, {});
