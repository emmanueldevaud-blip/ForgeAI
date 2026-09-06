import { ApiClient, ApiError } from './api.js';

const adApi = new ApiClient('/auth');

export async function getAdConfigs() {
  return adApi.get('/ad-configs');
}

export async function createAdConfig(configData) {
  return adApi.post('/ad-configs', configData);
}

export async function getAdConfig(configId) {
  return adApi.get(`/ad-configs/${configId}`);
}

export async function updateAdConfig(configId, updates) {
  return adApi.patch(`/ad-configs/${configId}`, updates);
}

export async function deleteAdConfig(configId) {
  return adApi.delete(`/ad-configs/${configId}`);
}

export async function getAdMappings(configId) {
  return adApi.get(`/ad-configs/${configId}/mappings`);
}

export async function createAdMapping(configId, mappingData) {
  return adApi.post(`/ad-configs/${configId}/mappings`, mappingData);
}

export async function deleteAdMapping(configId, mappingId) {
  return adApi.delete(`/ad-configs/${configId}/mappings/${mappingId}`);
}

export async function syncAdConfig(configId) {
  return adApi.post(`/ad-configs/${configId}/sync`);
}

export async function getAdSyncLogs(configId) {
  return adApi.get(`/ad-configs/${configId}/sync-logs`);
}

export async function testAdConfig(testData) {
  return adApi.post('/ad-configs/test', testData);
}

export { adApi, ApiError };