import { ApiClient } from './api.js';

const agendaApi = new ApiClient('/agenda');

export async function getAgendaPlanning(view = 'week', anchor = null) {
  const query = new URLSearchParams({ view });
  if (anchor) query.set('anchor', anchor);
  return agendaApi.get(`/planning?${query.toString()}`);
}

export async function upsertMyPresence(payload) {
  return agendaApi.post('/presences', payload);
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
