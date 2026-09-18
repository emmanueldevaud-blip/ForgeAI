import { ApiClient } from './api.js';

const dashboardApi = new ApiClient('/dashboard');

export async function getDashboardWidgets() {
  return dashboardApi.get('/widgets');
}

export async function getWidgetData(widgetId) {
  return dashboardApi.get(`/widgets/${encodeURIComponent(widgetId)}`);
}

export { dashboardApi };
