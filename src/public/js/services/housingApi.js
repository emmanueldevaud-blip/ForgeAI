import { ApiClient } from './api.js';

const housingApi = new ApiClient('/housing');

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

export async function listOccupancies(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.status) query.append('status', params.status);
  if (params.housing_id) query.append('housing_id', params.housing_id);
  if (params.occupant_id) query.append('occupant_id', params.occupant_id);
  if (params.date_from) query.append('date_from', params.date_from);
  if (params.date_to) query.append('date_to', params.date_to);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/occupancies${query.toString() ? '?' + query.toString() : ''}`;
  return housingApi.get(endpoint);
}

export async function getOccupancy(id) {
  return housingApi.get(`/occupancies/${id}`);
}

export async function createOccupancy(data) {
  return housingApi.post('/occupancies', data);
}

export async function updateOccupancy(id, data) {
  return housingApi.patch(`/occupancies/${id}`, data);
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

export async function getPlanning(startDate, endDate) {
  return housingApi.get(`/planning?start_date=${startDate}&end_date=${endDate}`);
}
