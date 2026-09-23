import { ApiClient } from './api.js?v=2';

const sportApi = new ApiClient('/sport');

export async function getSportDashboard(period = 28) {
  return sportApi.get(`/dashboard?period=${encodeURIComponent(period)}`);
}

export async function listSportActivities(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  return sportApi.get(`/activities${query.toString() ? `?${query}` : ''}`);
}

export async function analyzeSportActivity(activityId) {
  return sportApi.get(`/analysis/activities/${encodeURIComponent(activityId)}`);
}

export async function askSportCoach(question, conversationId = null) {
  return sportApi.post('/coach', { question, conversation_id: conversationId });
}

export async function getSportCoachConversation(conversationId) {
  return sportApi.get(`/coach/conversations/${encodeURIComponent(conversationId)}`);
}

export async function listSportCoachConversations() {
  return sportApi.get('/coach/conversations');
}

export async function getSportAthleteProfile() {
  return sportApi.get('/athlete/profile');
}

export async function updateSportHeartRateConfig(data) {
  return sportApi.put('/athlete/heart-rate', data);
}

export async function createSportActivity(data) {
  return sportApi.post('/activities', data);
}

export async function importSportActivity(file) {
  const formData = new FormData();
  formData.append('file', file);
  return sportApi.post('/activities/import', formData);
}

export async function listSportGoals() {
  return sportApi.get('/goals');
}

export async function getGarminConnection() {
  return sportApi.get('/garmin');
}

export async function connectGarmin(data) {
  return sportApi.post('/garmin/connect', data);
}

export async function syncGarmin() {
  return sportApi.post('/garmin/sync', {});
}

export async function disconnectGarmin() {
  return sportApi.delete('/garmin');
}
