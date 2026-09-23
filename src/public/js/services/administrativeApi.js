import { ApiClient } from './api.js';

const administrativeApi = new ApiClient('/administration');

export const listAdministrativeCapabilities = () => administrativeApi.get('/programs/capabilities');
export const createAdministrativeCapability = (data) => administrativeApi.post('/programs/capabilities', data);
export const listVolunteerCapabilities = (volunteerId) => administrativeApi.get(`/programs/volunteers/${volunteerId}/capabilities`);
export const assignVolunteerCapability = (volunteerId, data) => administrativeApi.post(`/programs/volunteers/${volunteerId}/capabilities`, data);
export const deleteVolunteerCapability = (volunteerId, capabilityId) => administrativeApi.delete(`/programs/volunteers/${volunteerId}/capabilities/${capabilityId}`);

export const listAdministrativeUnavailabilities = () => administrativeApi.get('/programs/unavailabilities');
export const createAdministrativeUnavailability = (data) => administrativeApi.post('/programs/unavailabilities', data);
export const deleteAdministrativeUnavailability = (id) => administrativeApi.delete(`/programs/unavailabilities/${id}`);

export const listAdministrativeProgramTypes = () => administrativeApi.get('/programs/types');
export const listAdministrativeRoles = () => administrativeApi.get('/programs/roles');
export const listAdministrativeSessions = (year, month) => administrativeApi.get(`/programs/sessions?year=${year}&month=${month}`);
export const createAdministrativeSession = (data) => administrativeApi.post('/programs/sessions', data);
export const generateAdministrativeSession = (id) => administrativeApi.post(`/programs/sessions/${id}/generate`);
export const validateAdministrativeSession = (id) => administrativeApi.post(`/programs/sessions/${id}/validate`);
export const updateAdministrativeAssignment = (id, data) => administrativeApi.put(`/programs/assignments/${id}`, data);
