import { ApiClient } from './api.js';

const aiApi = new ApiClient('/ai');

export async function sendAIMessage(data) {
  return aiApi.post('/chat', data);
}

export async function listAIConversations(params = {}) {
  const query = new URLSearchParams();
  if (params.module) query.append('module', params.module);
  const endpoint = `/conversations${query.toString() ? '?' + query.toString() : ''}`;
  return aiApi.get(endpoint);
}

export async function getAIConversation(id) {
  return aiApi.get(`/conversations/${id}`);
}

export async function deleteAIConversation(id) {
  return aiApi.delete(`/conversations/${id}`);
}

export async function getAIOptions() {
  return aiApi.get('/options');
}

export default aiApi;
