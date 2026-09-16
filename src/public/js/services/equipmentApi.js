import { ApiClient } from './api.js';

const equipmentApi = new ApiClient('/equipment');

export async function listEquipmentTypes(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  return equipmentApi.get(`/types?${query.toString()}`);
}

export async function getEquipmentType(id) {
  return equipmentApi.get(`/types/${id}`);
}

export async function createEquipmentType(data) {
  return equipmentApi.post('/types', data);
}

export async function updateEquipmentType(id, data) {
  return equipmentApi.patch(`/types/${id}`, data);
}

export async function listEquipments(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.equipment_type_id) query.set('equipment_type_id', params.equipment_type_id);
  if (params.status) query.set('status', params.status);
  if (params.room_id) query.set('room_id', params.room_id);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  const qs = query.toString();
  return equipmentApi.get(qs ? `?${qs}` : '');
}

export async function getEquipment(id) {
  return equipmentApi.get(`/${id}`);
}

export async function createEquipment(data) {
  return equipmentApi.post('', data);
}

export async function updateEquipment(id, data) {
  return equipmentApi.patch(`/${id}`, data);
}

export async function deactivateEquipment(id) {
  return equipmentApi.patch(`/${id}/deactivate`);
}

export async function deleteEquipment(id) {
  return equipmentApi.delete(`/${id}`);
}
