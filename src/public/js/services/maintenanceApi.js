import { ApiClient } from './api.js';

const maintenanceApi = new ApiClient('/maintenance');

// ============================================================
// DASHBOARD
// ============================================================

export async function getMaintenanceDashboard() {
  return maintenanceApi.get('/dashboard');
}

// ============================================================
// PROVIDERS
// ============================================================

export async function listProviders(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/providers${query.toString() ? '?' + query.toString() : ''}`;
  return maintenanceApi.get(endpoint);
}

export async function getProvider(id) {
  return maintenanceApi.get(`/providers/${id}`);
}

export async function createProvider(data) {
  return maintenanceApi.post('/providers', data);
}

export async function updateProvider(id, data) {
  return maintenanceApi.patch(`/providers/${id}`, data);
}

// ============================================================
// PARTS
// ============================================================

export async function listParts(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/parts${query.toString() ? '?' + query.toString() : ''}`;
  return maintenanceApi.get(endpoint);
}

export async function getPart(id) {
  return maintenanceApi.get(`/parts/${id}`);
}

export async function createPart(data) {
  return maintenanceApi.post('/parts', data);
}

export async function updatePart(id, data) {
  return maintenanceApi.patch(`/parts/${id}`, data);
}

// ============================================================
// CONTRACTS
// ============================================================

export async function listContracts(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.provider_id) query.append('provider_id', params.provider_id);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/contracts${query.toString() ? '?' + query.toString() : ''}`;
  return maintenanceApi.get(endpoint);
}

export async function getContract(id) {
  return maintenanceApi.get(`/contracts/${id}`);
}

export async function createContract(data) {
  return maintenanceApi.post('/contracts', data);
}

export async function updateContract(id, data) {
  return maintenanceApi.patch(`/contracts/${id}`, data);
}

// ============================================================
// REQUESTS
// ============================================================

export async function listRequests(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.status) query.append('status', params.status);
  if (params.priority) query.append('priority', params.priority);
  if (params.equipment_id) query.append('equipment_id', params.equipment_id);
  if (params.requested_by) query.append('requested_by', params.requested_by);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/requests${query.toString() ? '?' + query.toString() : ''}`;
  return maintenanceApi.get(endpoint);
}

export async function getRequest(id) {
  return maintenanceApi.get(`/requests/${id}`);
}

export async function createRequest(data) {
  return maintenanceApi.post('/requests', data);
}

export async function updateRequest(id, data) {
  return maintenanceApi.patch(`/requests/${id}`, data);
}

export async function createWorkOrderFromRequest(requestId, data) {
  return maintenanceApi.post(`/requests/${requestId}/create-work-order`, data || {});
}

// ============================================================
// WORK ORDERS
// ============================================================

export async function listWorkOrders(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.status) query.append('status', params.status);
  if (params.priority) query.append('priority', params.priority);
  if (params.maintenance_type) query.append('maintenance_type', params.maintenance_type);
  if (params.equipment_id) query.append('equipment_id', params.equipment_id);
  if (params.responsible_id) query.append('responsible_id', params.responsible_id);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/work-orders${query.toString() ? '?' + query.toString() : ''}`;
  return maintenanceApi.get(endpoint);
}

export async function getWorkOrder(id) {
  return maintenanceApi.get(`/work-orders/${id}`);
}

export async function createWorkOrder(data) {
  return maintenanceApi.post('/work-orders', data);
}

export async function updateWorkOrder(id, data) {
  return maintenanceApi.patch(`/work-orders/${id}`, data);
}

// ============================================================
// INTERVENANTS
// ============================================================

export async function addIntervenant(woId, data) {
  return maintenanceApi.post(`/work-orders/${woId}/intervenants`, data);
}

export async function updateIntervenant(id, data) {
  return maintenanceApi.patch(`/intervenants/${id}`, data);
}

export async function removeIntervenant(id) {
  return maintenanceApi.delete(`/intervenants/${id}`);
}

// ============================================================
// INTERVENTIONS
// ============================================================

export async function addIntervention(woId, data) {
  return maintenanceApi.post(`/work-orders/${woId}/interventions`, data);
}

// ============================================================
// WORK ORDER PARTS
// ============================================================

export async function addWorkOrderPart(woId, data) {
  return maintenanceApi.post(`/work-orders/${woId}/parts`, data);
}

export async function removeWorkOrderPart(id) {
  return maintenanceApi.delete(`/work-order-parts/${id}`);
}

// ============================================================
// COSTS
// ============================================================

export async function addCost(woId, data) {
  return maintenanceApi.post(`/work-orders/${woId}/costs`, data);
}

// ============================================================
// PLANS (Préventif)
// ============================================================

export async function listPlans(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.equipment_id) query.append('equipment_id', params.equipment_id);
  if (params.frequency) query.append('frequency', params.frequency);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);
  const endpoint = `/plans${query.toString() ? '?' + query.toString() : ''}`;
  return maintenanceApi.get(endpoint);
}

export async function getPlan(id) {
  return maintenanceApi.get(`/plans/${id}`);
}

export async function createPlan(data) {
  return maintenanceApi.post('/plans', data);
}

export async function updatePlan(id, data) {
  return maintenanceApi.patch(`/plans/${id}`, data);
}

// ============================================================
// AI ASSISTANT
// ============================================================

export async function sendAIMessage(data) {
  return maintenanceApi.post('/ai/chat', data);
}

export async function listAIConversations(params = {}) {
  const query = new URLSearchParams();
  if (params.module) query.append('module', params.module);
  const endpoint = `/ai/conversations${query.toString() ? '?' + query.toString() : ''}`;
  return maintenanceApi.get(endpoint);
}

export async function getAIConversation(id) {
  return maintenanceApi.get(`/ai/conversations/${id}`);
}
