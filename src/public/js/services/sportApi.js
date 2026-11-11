import { ApiClient } from './api.js?v=2';

const sportApi = new ApiClient('/sport');
// Routes Community Manager enregistrées sur /community-manager (sans préfixe /sport)
const cmApi = new ApiClient('');

export async function listSportAnalyses(limit = 30) {
  return sportApi.get(`/analyses?limit=${encodeURIComponent(limit)}`);
}

export async function getSportDashboard(period = 28) {
  return sportApi.get(`/dashboard?period=${encodeURIComponent(period)}`);
}

export async function getSportHealth(period = 28) {
  return sportApi.get(`/health?period=${encodeURIComponent(period)}`);
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

export async function createSportGoal(data) {
  return sportApi.post('/goals', data);
}

export async function getSportGoalsAnalysis() {
  return sportApi.get('/analysis/goals');
}

export async function getInstagramAuthUrl() {
  return sportApi.get('/publications/meta/auth');
}

export async function getInstagramConnectionStatus() {
  return sportApi.get('/publications/meta/status');
}

export async function disconnectInstagram() {
  return sportApi.delete('/publications/meta');
}

export async function getGarminConnection() {
  return sportApi.get('/garmin');
}

export async function connectGarmin(data) {
  return sportApi.post('/garmin/connect', data);
}

export async function syncGarmin(fullHistory = false) {
  return sportApi.post(`/garmin/sync${fullHistory ? '?full_history=true' : ''}`, {});
}

export async function disconnectGarmin() {
  return sportApi.delete('/garmin');
}

export async function getSportNotificationConfig() {
  return sportApi.get('/notifications/config');
}

export async function generateVapidKeys() {
  return sportApi.post('/notifications/config/generate', {});
}

export async function updateSportNotificationConfig(data) {
  return sportApi.put('/notifications/config', data);
}

// --------------------------------------------------------------------------- #
// Publications Instagram
// --------------------------------------------------------------------------- #

export async function listPublicationStyles() {
  return sportApi.get('/publications/styles');
}

export async function getPublicationSettings() {
  return sportApi.get('/publications/settings');
}

export async function updatePublicationSettings(data) {
  return sportApi.put('/publications/settings', data);
}

export async function listPublications(params = {}) {
  const query = new URLSearchParams();
  if (params.status) query.append('status', params.status);
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  return sportApi.get(`/publications${query.toString() ? `?${query}` : ''}`);
}

export async function listRecentActivitiesForPublication(limit = 20) {
  return sportApi.get(`/publications/activities?limit=${encodeURIComponent(limit)}`);
}

export async function getPublicationForActivity(activityId) {
  return sportApi.get(`/publications/activity/${encodeURIComponent(activityId)}`);
}

export async function generatePublication(activityId, data) {
  return sportApi.post(`/publications/activity/${encodeURIComponent(activityId)}/generate`, data);
}

export async function getPublication(id) {
  return sportApi.get(`/publications/${encodeURIComponent(id)}`);
}

export async function updatePublication(id, data) {
  return sportApi.patch(`/publications/${encodeURIComponent(id)}`, data);
}

export async function validatePublication(id) {
  return sportApi.post(`/publications/${encodeURIComponent(id)}/validate`, {});
}

export async function markPublicationShared(id) {
  return sportApi.post(`/publications/${encodeURIComponent(id)}/share`, {});
}

export async function generatePublicationCard(id) {
  return sportApi.post(`/publications/${encodeURIComponent(id)}/card`, {});
}

export async function deletePublication(id) {
  return sportApi.delete(`/publications/${encodeURIComponent(id)}`);
}

export function publicationPhotoUrl(id, size = 'medium') {
  return `/photos/${id}/file?size=${encodeURIComponent(size)}`;
}

// --------------------------------------------------------------------------- #
// Community Manager IA (V1)
// --------------------------------------------------------------------------- #

// V1 : Récupération stratégie
export async function loadCommunityStrategy(athleteId) {
  return sportApi.get(`/publications/community-strategy?athlete_id=${encodeURIComponent(athleteId)}`);
}

// V1 : Génération de sujets IA
export async function generateCommunityTopics(count = 5) {
  return sportApi.post('/publications/community-generate', { count });
}

// V1 : Récupération calendrier
export async function getCommunityCalendar(athleteId) {
  return sportApi.get(`/publications/community-calendar?athlete_id=${encodeURIComponent(athleteId)}`);
}

// V1 : Routes directes Community Manager (nouvelles routes V1)
export async function getCommunityManagerStrategy() {
  return cmApi.get('/community-manager/strategy');
}

export async function updateCommunityManagerStrategy(data) {
  return cmApi.put('/community-manager/strategy', data);
}

export async function generateCommunityManagerCalendar(count = 5) {
  return cmApi.post('/community-manager/generate-calendar', { count });
}

export async function getCommunityManagerCalendar() {
  return cmApi.get('/community-manager/calendar');
}

export async function updateCommunityManagerCalendarEntry(entryId, data) {
  return cmApi.patch(`/community-manager/calendar/${encodeURIComponent(entryId)}`, data);
}

export async function deleteCommunityManagerCalendarEntry(entryId) {
  return cmApi.delete(`/community-manager/calendar/${encodeURIComponent(entryId)}`);
}

// --------------------------------------------------------------------------- #
// Community Manager V2 - Studio de création
// --------------------------------------------------------------------------- #

// V2 : Créer un brouillon depuis une entrée de calendrier
export async function createStudioDraftFromCalendar(data) {
  return cmApi.post('/community-manager/studio/from-calendar', data);
}

// V2 : Récupérer un brouillon
export async function getStudioDraft(publicationId) {
  return cmApi.get(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}`);
}

// V2 : Mettre à jour un brouillon
export async function updateStudioDraft(publicationId, data) {
  return cmApi.patch(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}`, data);
}

// V2 : Générer des variantes de texte
export async function generateStudioDraftVariants(publicationId, data) {
  return cmApi.post(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/variants`, data);
}

// V2 : Valider un brouillon pour publication
export async function validateStudioDraft(publicationId, data) {
  return cmApi.post(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/validate`, data);
}

// V2 : Planifier une publication
export async function scheduleStudioDraft(publicationId, scheduledAt) {
  return cmApi.post(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/schedule`, { scheduled_at: scheduledAt });
}

// V2 : Prévisualiser le rendu Instagram
export async function previewStudioDraft(publicationId, format = 'feed') {
  return cmApi.post(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/preview`, { format });
}

// V2 : Publier sur Instagram
export async function publishStudioDraft(publicationId, data) {
  return cmApi.post(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/publish`, data);
}

// --------------------------------------------------------------------------- #
// Community Manager V3 - Lock/Unlock & Text Generation
// --------------------------------------------------------------------------- #

// V3 : Verrouiller/Déverrouiller le titre
export async function lockStudioDraftTitle(publicationId, locked) {
  return cmApi.patch(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/lock/title`, null, { params: { locked } });
}

// V3 : Verrouiller/Déverrouiller le contenu
export async function lockStudioDraftContent(publicationId, locked) {
  return cmApi.patch(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/lock/content`, null, { params: { locked } });
}

// V3 : Verrouiller/Déverrouiller le visuel
export async function lockStudioDraftPhoto(publicationId, locked) {
  return cmApi.patch(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/lock/photo`, null, { params: { locked } });
}

// V3 : Générer un texte (court ou long) selon le ton
export async function generateStudioDraftText(publicationId, data) {
  return cmApi.post(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/generate-text`, data);
}

// V3 : Photos suggérées liées aux activités Garmin et dates
export async function getSuggestedPhotos(publicationId, limit = 15) {
  return cmApi.get(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/suggested-photos`, { params: { limit } });
}

// --------------------------------------------------------------------------- #
// Community Manager V4 - Calendrier mensuel/hebdomadaire + Suggestions
// --------------------------------------------------------------------------- #

export async function getMonthCalendar(year, month) {
  return cmApi.get(`/community-manager/calendar/month?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}`);
}

export async function getWeekCalendar(monday) {
  return cmApi.get(`/community-manager/calendar/week?monday=${encodeURIComponent(monday)}`);
}

export async function generateSuggestions() {
  return cmApi.post('/community-manager/suggestions/generate', {});
}

export async function acceptSuggestion(entryId) {
  return cmApi.post(`/community-manager/suggestions/${encodeURIComponent(entryId)}/accept`);
}

export async function refuseSuggestion(entryId) {
  return cmApi.post(`/community-manager/suggestions/${encodeURIComponent(entryId)}/refuse`);
}

export async function rescheduleSuggestion(entryId, newDate) {
  return cmApi.post(`/community-manager/suggestions/${encodeURIComponent(entryId)}/reschedule?new_date=${encodeURIComponent(newDate)}`);
}

export async function regeneratePublicationContent(publicationId) {
  return cmApi.post(`/community-manager/studio/draft/${encodeURIComponent(publicationId)}/regenerate`);
}
