import { ApiClient } from './api.js';

const agendaApi = new ApiClient('/agenda');

export async function getAgendaPlanning(view = 'week', anchor = null) {
  const query = new URLSearchParams({ view });
  if (anchor) query.set('anchor', anchor);
  query.set('_', Date.now().toString());
  return agendaApi.get(`/planning?${query.toString()}`);
}

export async function getAgendaSynthesis(view = 'week', anchor = null) {
  const query = new URLSearchParams({ view });
  if (anchor) query.set('anchor', anchor);
  query.set('_', Date.now().toString());
  return agendaApi.get(`/synthesis?${query.toString()}`);
}

export async function upsertMyPresence(payload) {
  return agendaApi.post('/presences', payload);
}

export async function autoAssignMyPresences(startDate, endDate) {
  return agendaApi.post('/presences/auto-assign', {
    start_date: startDate,
    end_date: endDate,
  });
}

export async function createExternalPresence(payload) {
  return agendaApi.post('/presences/external', payload);
}

export async function updatePresence(presenceId, payload) {
  return agendaApi.patch(`/presences/${presenceId}`, payload);
}

export async function deletePresence(presenceId) {
  return agendaApi.delete(`/presences/${presenceId}`);
}

export async function getAgendaSettings() {
  return agendaApi.get('/settings');
}

export async function updateAgendaSettings(planningGroupIds) {
  return agendaApi.put('/settings', { planning_group_ids: planningGroupIds });
}

export async function getAgendaGroups() {
  return agendaApi.get('/groups');
}

export async function analyzeImport(file) {
  const form = new FormData();
  form.append('file', file);
  return agendaApi.post('/imports', form, { headers: { 'Content-Type': 'multipart/form-data' } });
}

export async function listImports() {
  return agendaApi.get('/imports');
}

export async function getImport(batchId) {
  return agendaApi.get(`/imports/${batchId}`);
}

export async function getImportRows(batchId, params = {}) {
  const query = new URLSearchParams(params);
  return agendaApi.get(`/imports/${batchId}/rows?${query.toString()}`);
}

export async function updateImportRow(batchId, rowId, payload) {
  return agendaApi.patch(`/imports/${batchId}/rows/${rowId}`, payload);
}

export async function validateImport(batchId) {
  return agendaApi.post(`/imports/${batchId}/validate`);
}
