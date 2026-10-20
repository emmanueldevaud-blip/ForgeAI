import { ApiClient } from './api.js';

const api = new ApiClient('/intendance/expenses');

export const listExpenses = (params = {}) => api.get(`?${new URLSearchParams(params)}`);
export const getExpenseDashboard = (params = {}) => api.get(`/dashboard?${new URLSearchParams(params)}`);
export const getMealCostBySite = (params = {}) => api.get(`/dashboard/meal-cost-by-site?${new URLSearchParams(params)}`);
export const listCategories = () => api.get('/categories');
export const createCategory = data => api.post('/categories', data);
export const updateCategory = (id, data) => api.patch(`/categories/${id}`, data);
export const updateUncategorizedCategory = data => api.patch('/categories/uncategorized', data);
export const deleteCategory = id => api.delete(`/categories/${id}`);
export const updateExpense = (id, data) => api.patch(`/${id}`, data);
export const deleteExpense = id => api.delete(`/${id}`);
export const listSites = () => api.get('/sites');
export const listAccountCodes = () => api.get('/account-codes');
export const listAliases = () => api.get('/aliases');
export const createAccountCode = data => api.post('/account-codes', data);
export const updateAccountCode = (id, data) => api.patch(`/account-codes/${id}`, data);
export const deleteAccountCode = id => api.delete(`/account-codes/${id}`);
export const createAlias = data => api.post('/aliases', data);
export const updateAlias = (id, data) => api.patch(`/aliases/${id}`, data);
export const deleteAlias = id => api.delete(`/aliases/${id}`);
export const createSite = data => api.post('/sites', data);
export const updateSite = (id, data) => api.patch(`/sites/${id}`, data);
export const deleteSite = id => api.delete(`/sites/${id}`);
export const assignSites = (ids, site_id) => api.post('/sites/bulk', { ids, site_id });
export const analyzeImport = (file) => {
  const form = new FormData(); form.append('file', file);
  return api.post('/imports', form);
};
export const validateImport = (id) => api.post(`/imports/${id}/validate`, {});
export const reassignReferences = () => api.post('/reassign', {});
