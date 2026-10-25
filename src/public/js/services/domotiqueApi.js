import { ApiClient } from './api.js?v=2';

const domotiqueApi = new ApiClient('/domotique');

export async function getDomotiqueStatus(code = 'sechoir-saucisson') {
  return domotiqueApi.get(`/status?code=${encodeURIComponent(code)}`);
}

export async function getDomotiqueHistory(period = '24h', code = 'sechoir-saucisson') {
  return domotiqueApi.get(`/history?period=${encodeURIComponent(period)}&code=${encodeURIComponent(code)}`);
}

export async function listDomotiqueEvents(limit = 50, code = 'sechoir-saucisson') {
  return domotiqueApi.get(`/events?limit=${limit}&code=${encodeURIComponent(code)}`);
}

export async function getDomotiqueCycle(code = 'sechoir-saucisson') {
  return domotiqueApi.get(`/cycle?code=${encodeURIComponent(code)}`);
}

export async function listDomotiqueCycles(limit = 20, code = 'sechoir-saucisson') {
  return domotiqueApi.get(`/cycles?limit=${limit}&code=${encodeURIComponent(code)}`);
}

export async function createDomotiqueCycle(payload) {
  return domotiqueApi.post('/cycle', payload);
}

export async function startDomotiqueCycle(payload = {}) {
  return domotiqueApi.post('/cycle/start', payload);
}

export async function pauseDomotiqueCycle(payload = {}) {
  return domotiqueApi.post('/cycle/pause', payload);
}

export async function stopDomotiqueCycle(payload = {}) {
  return domotiqueApi.post('/cycle/stop', payload);
}

export async function advanceDomotiqueCycle(payload = {}) {
  return domotiqueApi.post('/cycle/advance', payload);
}

export async function sendDomotiqueManual(payload) {
  return domotiqueApi.post('/manual', payload);
}

export async function setDomotiqueOutputMode(index, mode) {
  return domotiqueApi.post(`/outputs/${index}/mode`, { mode });
}

export async function listDomotiqueProfiles() {
  return domotiqueApi.get('/profiles');
}

export async function createDomotiqueProfile(payload) {
  return domotiqueApi.post('/profiles', payload);
}

export async function updateDomotiqueProfile(profileId, payload) {
  return domotiqueApi.put(`/profiles/${profileId}`, payload);
}

export async function deleteDomotiqueProfile(profileId) {
  return domotiqueApi.delete(`/profiles/${profileId}`);
}

export async function getDomotiqueConfig(code = 'sechoir-saucisson') {
  return domotiqueApi.get(`/config?code=${encodeURIComponent(code)}`);
}

export async function updateDomotiqueConfig(payload, code = 'sechoir-saucisson') {
  return domotiqueApi.put(`/config?code=${encodeURIComponent(code)}`, payload);
}

export async function testDomotiqueConnection(payload = {}, code = 'sechoir-saucisson') {
  return domotiqueApi.post(`/config/test?code=${encodeURIComponent(code)}`, payload);
}

export async function updateDomotiqueOutput(outputId, payload) {
  return domotiqueApi.put(`/outputs/${outputId}`, payload);
}

export async function updateDomotiqueSensor(sensorId, payload) {
  return domotiqueApi.put(`/sensors/${sensorId}`, payload);
}

export function listSurveillanceCameras() { return domotiqueApi.get('/surveillance/cameras'); }
export function createSurveillanceCamera(payload) { return domotiqueApi.post('/surveillance/cameras', payload); }
export function updateSurveillanceCamera(id, payload) { return domotiqueApi.put(`/surveillance/cameras/${id}`, payload); }
export function deleteSurveillanceCamera(id) { return domotiqueApi.delete(`/surveillance/cameras/${id}`); }
export function testSurveillanceCamera(id) { return domotiqueApi.post(`/surveillance/cameras/${id}/test`, {}); }
export function getSurveillanceCapture(id) { return domotiqueApi.get(`/surveillance/cameras/${id}/capture`); }
export function startSurveillanceCapture(id) { return domotiqueApi.post(`/surveillance/cameras/${id}/capture/start`, {}); }
export function stopSurveillanceCapture(id) { return domotiqueApi.post(`/surveillance/cameras/${id}/capture/stop`, {}); }
export function listSurveillanceEvents(limit = 50) { return domotiqueApi.get(`/surveillance/events?limit=${limit}`); }
export function listSurveillanceRecordings(limit = 50) { return domotiqueApi.get(`/surveillance/recordings?limit=${limit}`); }
