import { ApiClient } from './api.js';

const agendaApi = new ApiClient('/agenda');

export async function getAgendaPlanning(view = 'week', anchor = null) {
  const query = new URLSearchParams({ view });
  if (anchor) query.set('anchor', anchor);
  query.set('_', Date.now().toString());
  return agendaApi.get(`/planning?${query.toString()}`);
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
