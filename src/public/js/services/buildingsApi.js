import { ApiClient } from './api.js';

const buildingsApi = new ApiClient('/buildings');

export async function listSites(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  return buildingsApi.get(`/sites?${query.toString()}`);
}

export async function getSite(id) {
  return buildingsApi.get(`/sites/${id}`);
}

export async function createSite(data) {
  return buildingsApi.post('/sites', data);
}

export async function updateSite(id, data) {
  return buildingsApi.patch(`/sites/${id}`, data);
}

export async function deleteSite(id) {
  return buildingsApi.delete(`/sites/${id}`);
}

export async function listBuildings(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.site_id) query.set('site_id', params.site_id);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  const qs = query.toString();
  return buildingsApi.get(qs ? `?${qs}` : '');
}

export async function getBuilding(id) {
  return buildingsApi.get(`/${id}`);
}

export async function createBuilding(data) {
  return buildingsApi.post('', data);
}

export async function updateBuilding(id, data) {
  return buildingsApi.patch(`/${id}`, data);
}

export async function deleteBuilding(id) {
  return buildingsApi.delete(`/${id}`);
}

export async function listRooms(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.building_id) query.set('building_id', params.building_id);
  if (params.usage_type_id) query.set('usage_type_id', params.usage_type_id);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.used_for_accommodation !== undefined) query.set('used_for_accommodation', params.used_for_accommodation);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  return buildingsApi.get(`/rooms?${query.toString()}`);
}

export async function getRoom(id) {
  return buildingsApi.get(`/rooms/${id}`);
}

export async function createRoom(data) {
  return buildingsApi.post('/rooms', data);
}

export async function updateRoom(id, data) {
  return buildingsApi.patch(`/rooms/${id}`, data);
}

export async function deleteRoom(id, force = false) {
  return buildingsApi.delete(`/rooms/${id}${force ? '?force=true' : ''}`);
}

export async function listUsageTypes(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  return buildingsApi.get(`/usage-types?${query.toString()}`);
}

export async function createUsageType(data) {
  return buildingsApi.post('/usage-types', data);
}

export async function updateUsageType(id, data) {
  return buildingsApi.patch(`/usage-types/${id}`, data);
}

export async function deleteUsageType(id) {
  return buildingsApi.delete(`/usage-types/${id}`);
}

export async function listRoomTypes(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  return buildingsApi.get(`/room-types?${query.toString()}`);
}

export async function getRoomType(id) {
  return buildingsApi.get(`/room-types/${id}`);
}

export async function createRoomType(data) {
  return buildingsApi.post('/room-types', data);
}

export async function updateRoomType(id, data) {
  return buildingsApi.patch(`/room-types/${id}`, data);
}

export async function deleteRoomType(id) {
  return buildingsApi.delete(`/room-types/${id}`);
}
