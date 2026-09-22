import { ApiClient } from './api.js?v=2';

const housingApi = new ApiClient('/housing');
const volunteerApi = new ApiClient('/volunteers');

// ============================================================
// DASHBOARD
// ============================================================

export async function getHousingDashboard() {
  return housingApi.get('/dashboard');
}

// ============================================================
// HOUSINGS
// ============================================================

export async function listHousings(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.site_id) query.append('site_id', params.site_id);
  if (params.building_id) query.append('building_id', params.building_id);
  if (params.housing_type) query.append('housing_type', params.housing_type);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/housings${query.toString() ? '?' + query.toString() : ''}`;
  return housingApi.get(endpoint);
}

export async function getHousing(id) {
  return housingApi.get(`/housings/${id}`);
}

export async function createHousing(data) {
  return housingApi.post('/housings', data);
}

export async function updateHousing(id, data) {
  return housingApi.patch(`/housings/${id}`, data);
}

// ============================================================
// OCCUPANTS
// ============================================================

export async function listOccupants(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/occupants${query.toString() ? '?' + query.toString() : ''}`;
  return housingApi.get(endpoint);
}

export async function getOccupant(id) {
  return housingApi.get(`/occupants/${id}`);
}

export async function createOccupant(data) {
  return housingApi.post('/occupants', data);
}

export async function updateOccupant(id, data) {
  return housingApi.patch(`/occupants/${id}`, data);
}

// ============================================================
// OCCUPANCIES
// ============================================================

export async function createOccupancy(data) {
  return housingApi.post('/occupancies', data);
}

export async function updateOccupancy(id, data) {
  return housingApi.patch(`/occupancies/${id}`, data);
}

export async function deleteOccupancy(id) {
  return housingApi.delete(`/occupancies/${id}`);
}

export async function changeOccupancyStatus(id, status) {
  return housingApi.post(`/occupancies/${id}/status`, { status });
}

// ============================================================
// UNAVAILABILITIES
// ============================================================

export async function listUnavailabilities(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.housing_id) query.append('housing_id', params.housing_id);
  if (params.reason) query.append('reason', params.reason);
  if (params.date_from) query.append('date_from', params.date_from);
  if (params.date_to) query.append('date_to', params.date_to);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/unavailabilities${query.toString() ? '?' + query.toString() : ''}`;
  return housingApi.get(endpoint);
}

export async function createUnavailability(data) {
  return housingApi.post('/unavailabilities', data);
}

export async function deleteUnavailability(id) {
  return housingApi.delete(`/unavailabilities/${id}`);
}

// ============================================================
// PLANNING
// ============================================================

export async function getPlanning(startDate, endDate, view = 'month', housingIds = null, statusFilter = null) {
  let url = `/planning?start_date=${startDate}&end_date=${endDate}&view=${view}`;
  if (housingIds) url += `&housing_ids=${encodeURIComponent(JSON.stringify(housingIds))}`;
  if (statusFilter) url += `&status_filter=${statusFilter}`;
  return housingApi.get(url);
}

// ============================================================
// CLEANING
// ============================================================

export async function listCleanings(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.housing_id) query.append('housing_id', params.housing_id);
  if (params.occupancy_id) query.append('occupancy_id', params.occupancy_id);
  if (params.type) query.append('type', params.type);
  if (params.status) query.append('status', params.status);
  if (params.date_from) query.append('date_from', params.date_from);
  if (params.date_to) query.append('date_to', params.date_to);
  if (params.assigned_to) query.append('assigned_to', params.assigned_to);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/cleanings${query.toString() ? '?' + query.toString() : ''}`;
  return housingApi.get(endpoint);
}

export async function getCleaning(id) {
  return housingApi.get(`/cleanings/${id}`);
}

export async function createCleaning(data) {
  return housingApi.post('/cleanings', data);
}

export async function updateCleaning(id, data) {
  return housingApi.patch(`/cleanings/${id}`, data);
}

export async function deleteCleaning(id) {
  return housingApi.delete(`/cleanings/${id}`);
}

// ============================================================
// EMAIL TEMPLATES
// ============================================================

export async function listEmailTemplates(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.template_type) query.append('template_type', params.template_type);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/email-templates${query.toString() ? '?' + query.toString() : ''}`;
  return housingApi.get(endpoint);
}

export async function getEmailTemplate(id) {
  return housingApi.get(`/email-templates/${id}`);
}

export async function createEmailTemplate(data) {
  return housingApi.post('/email-templates', data);
}

export async function updateEmailTemplate(id, data) {
  return housingApi.patch(`/email-templates/${id}`, data);
}

export async function uploadEmailTemplateAttachment(templateId, file, housingIds = []) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('housing_ids', JSON.stringify(housingIds));
  return housingApi.post(`/email-templates/${templateId}/attachments`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
}

export async function updateEmailTemplateAttachmentHousings(templateId, attachmentId, housingIds) {
  return housingApi.put(`/email-templates/${templateId}/attachments/${attachmentId}`, housingIds);
}

export async function deleteEmailTemplateAttachment(templateId, attachmentId) {
  return housingApi.delete(`/email-templates/${templateId}/attachments/${attachmentId}`);
}

// ============================================================
// EMAIL SENDING
// ============================================================

export async function sendConfirmationEmail(occupancyId, templateId, recipientIds, sendToAll) {
  const formData = new FormData();
  formData.append('template_id', templateId);
  formData.append('recipient_ids', JSON.stringify(recipientIds));
  formData.append('send_to_all', sendToAll);
  return housingApi.post(`/occupancies/${occupancyId}/send-confirmation`, formData);
}

export async function sendCustomMessage(occupancyId, subject, bodyText, recipientIds, templateId = null, attachmentIds = []) {
  const formData = new FormData();
  formData.append('subject', subject);
  formData.append('body_text', bodyText);
  formData.append('recipient_ids', JSON.stringify(recipientIds));
  if (templateId) formData.append('template_id', templateId);
  formData.append('attachment_ids', JSON.stringify(attachmentIds));
  return housingApi.post(`/occupancies/${occupancyId}/send-message`, formData);
}

export async function listEmailLogs(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.template_id) query.append('template_id', params.template_id);
  if (params.occupancy_id) query.append('occupancy_id', params.occupancy_id);
  if (params.status) query.append('status', params.status);
  if (params.date_from) query.append('date_from', params.date_from);
  if (params.date_to) query.append('date_to', params.date_to);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/email-logs${query.toString() ? '?' + query.toString() : ''}`;
  return housingApi.get(endpoint);
}

// ============================================================
// QUICK OCCUPANT
// ============================================================

export async function quickCreateOccupant(data) {
  return housingApi.post('/occupants/quick-create', data);
}

// ============================================================
// VOLUNTEERS
// ============================================================

export async function listVolunteers(params = {}) {
  const query = new URLSearchParams();
  if (params.skip) query.append('skip', params.skip);
  if (params.limit) query.append('limit', params.limit);
  const endpoint = `/${query.toString() ? '?' + query.toString() : ''}`;
  return volunteerApi.get(endpoint);
}

export async function createVolunteer(data) {
  return volunteerApi.post('/', data);
}

export async function updateVolunteer(id, data) {
  return volunteerApi.put(`/${id}`, data);
}

export async function deleteVolunteer(id) {
  return volunteerApi.delete(`/${id}`);
}
