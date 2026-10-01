import { ApiClient } from './api.js';

const developmentApi = new ApiClient('/development');

// ============================================================
// DEVELOPMENT AGENT
// ============================================================

export async function getDevelopmentStatus() {
  return developmentApi.get('/status');
}

export async function commitDevelopment(data) {
  return developmentApi.post('/commit', data);
}

export async function deployDevelopment(data) {
  return developmentApi.post('/deploy', data);
}
