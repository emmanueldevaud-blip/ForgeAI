import { ApiClient } from './api.js';

const itAssetApi = new ApiClient('/it-assets');

export async function listItAssets(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.asset_type) query.set('asset_type', params.asset_type);
  if (params.status) query.set('status', params.status);
  if (params.room_id) query.set('room_id', params.room_id);
  if (params.site_id) query.set('site_id', params.site_id);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  const qs = query.toString();
  return itAssetApi.get(qs ? `?${qs}` : '');
}

export async function getItAsset(id) {
  return itAssetApi.get(`/${id}`);
}

export async function createItAsset(data) {
  return itAssetApi.post('', data);
}

export async function updateItAsset(id, data) {
  return itAssetApi.patch(`/${id}`, data);
}

export async function deleteItAsset(id) {
  return itAssetApi.delete(`/${id}`);
}

export async function importItAssets(data) {
  return itAssetApi.post('/import', data);
}

export async function getAssetObservations(assetId, limit = 100) {
  return itAssetApi.get(`/${assetId}/observations?limit=${limit}`);
}

export async function getAssetAlerts(assetId, resolved = null) {
  const query = new URLSearchParams();
  if (resolved !== null) query.set('resolved', resolved);
  const qs = query.toString();
  return itAssetApi.get(`/${assetId}/alerts${qs ? `?${qs}` : ''}`);
}

export async function acknowledgeAlert(assetId, alertId) {
  return itAssetApi.patch(`/${assetId}/alerts/${alertId}/acknowledge`, { acknowledged: true });
}

export async function resolveAlert(assetId, alertId) {
  return itAssetApi.patch(`/${assetId}/alerts/${alertId}/resolve`, { resolved: true });
}

export async function getAssetHistory(assetId, limit = 100) {
  return itAssetApi.get(`/${assetId}/history?limit=${limit}`);
}

export async function checkAsset(assetId) {
  return itAssetApi.post(`/${assetId}/check`);
}

export async function monitorAllAssets() {
  return itAssetApi.post('/monitor');
}

export async function listNetworkRanges(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.page_size) query.set('page_size', params.page_size);
  if (params.search) query.set('search', params.search);
  if (params.is_active !== undefined) query.set('is_active', params.is_active);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.sort_order) query.set('sort_order', params.sort_order);
  const qs = query.toString();
  return itAssetApi.get(`/network-ranges${qs ? `?${qs}` : ''}`);
}

export async function getNetworkRange(id) {
  return itAssetApi.get(`/network-ranges/${id}`);
}

export async function createNetworkRange(data) {
  return itAssetApi.post('/network-ranges', data);
}

export async function updateNetworkRange(id, data) {
  return itAssetApi.patch(`/network-ranges/${id}`, data);
}

export async function deleteNetworkRange(id) {
  return itAssetApi.delete(`/network-ranges/${id}`);
}

export async function scanNetworkRange(rangeId) {
  return itAssetApi.post(`/network-ranges/${rangeId}/scan`);
}

export async function getDiscoveryLogs(rangeId, limit = 50) {
  return itAssetApi.get(`/network-ranges/${rangeId}/logs?limit=${limit}`);
}

export async function discoverAllRanges() {
  return itAssetApi.post('/discover');
}

export async function setManagementUrl(assetId, managementUrl) {
  return itAssetApi.patch(`/${assetId}/management-url`, { management_url: managementUrl });
}

export async function detectManagementUrl(assetId) {
  return itAssetApi.post(`/${assetId}/management-url/detect`);
}

export async function checkManagementUrl(assetId) {
  return itAssetApi.post(`/${assetId}/management-url/check`);
}

export async function wakeItAsset(assetId) {
  return itAssetApi.post(`/${assetId}/wake`);
}

export async function shutdownItAsset(assetId, data = {}) {
  return itAssetApi.post(`/${assetId}/shutdown`, data);
}

export function getAssetRdpUrl(assetId) {
  return `/it-assets/${assetId}/rdp`;
}
