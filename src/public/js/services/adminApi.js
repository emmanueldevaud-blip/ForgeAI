import { ApiClient, ApiError } from './api.js';

const adminApi = new ApiClient('/admin');

export async function getUser(userId) {
  return adminApi.get(`/users/${userId}`);
}

export async function listUsers(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.role) query.append('role', params.role);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.source) query.append('source', params.source);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);

  const endpoint = `/users${query.toString() ? '?' + query.toString() : ''}`;
  return adminApi.get(endpoint);
}

export async function createUser(userData) {
  return adminApi.post('/users', userData);
}

export async function updateUser(userId, updates) {
  return adminApi.patch(`/users/${userId}`, updates);
}

export async function deleteUser(userId) {
  return adminApi.delete(`/users/${userId}`);
}

export async function toggleUserActive(userId, isActive) {
  return adminApi.post(`/users/${userId}/toggle-active`, { is_active: isActive });
}

export async function resetUserPassword(userId, newPassword) {
  return adminApi.post(`/users/${userId}/reset-password`, { new_password: newPassword });
}

export async function listRoles() {
  const response = await adminApi.get('/users/roles');

  return Array.isArray(response)
    ? response
    : (response.roles || []);
}

export async function assignRoleToUser(userId, roleId) {
  return adminApi.post(`/users/${userId}/roles`, { role_id: roleId });
}

export async function removeRoleFromUser(userId, roleId) {
  return adminApi.delete(`/users/${userId}/roles/${roleId}`);
}

export async function getUserPermissions(userId) {
  return adminApi.get(`/users/${userId}/permissions`);
}

// Groups API
export async function listGroups(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);

  const endpoint = `/users/groups${query.toString() ? '?' + query.toString() : ''}`;
  return adminApi.get(endpoint);
}

export async function createGroup(groupData) {
  return adminApi.post('/users/groups', groupData);
}

export async function getGroup(groupId) {
  return adminApi.get(`/users/groups/${groupId}`);
}

export async function updateGroup(groupId, updates) {
  return adminApi.patch(`/users/groups/${groupId}`, updates);
}

export async function deleteGroup(groupId) {
  return adminApi.delete(`/users/groups/${groupId}`);
}

export async function addUserToGroup(groupId, userId) {
  return adminApi.post(`/users/groups/${groupId}/users`, { user_id: userId });
}

export async function removeUserFromGroup(groupId, userId) {
  return adminApi.delete(`/users/groups/${groupId}/users/${userId}`);
}

export async function addRoleToGroup(groupId, roleId) {
  return adminApi.post(`/users/groups/${groupId}/roles`, { role_id: roleId });
}

export async function removeRoleFromGroup(groupId, roleId) {
  return adminApi.delete(`/users/groups/${groupId}/roles/${roleId}`);
}

// Roles API
export async function listRolesAdmin(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.is_active !== undefined && params.is_active !== null) query.append('is_active', params.is_active);
  if (params.is_system !== undefined && params.is_system !== null) query.append('is_system', params.is_system);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);

  const endpoint = `/users/roles${query.toString() ? '?' + query.toString() : ''}`;
  return adminApi.get(endpoint);
}

export async function createRole(roleData) {
  return adminApi.post('/users/roles', roleData);
}

export async function getRole(roleId) {
  return adminApi.get(`/users/roles/${roleId}`);
}

export async function updateRole(roleId, updates) {
  return adminApi.patch(`/users/roles/${roleId}`, updates);
}

export async function deleteRole(roleId) {
  return adminApi.delete(`/users/roles/${roleId}`);
}

export async function addPermissionToRole(roleId, permissionId) {
  return adminApi.post(`/users/roles/${roleId}/permissions`, { permission_id: permissionId });
}

export async function removePermissionFromRole(roleId, permissionId) {
  return adminApi.delete(`/users/roles/${roleId}/permissions/${permissionId}`);
}

export async function replaceRolePermissions(roleId, permissionIds) {
  return adminApi.put(`/users/roles/${roleId}/permissions`, { permission_ids: permissionIds });
}

export async function listRolePermissions(roleId) {
  return adminApi.get(`/users/roles/${roleId}/permissions`);
}

// Permissions API
export async function listPermissions(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.append('page', params.page);
  if (params.page_size) query.append('page_size', params.page_size);
  if (params.search) query.append('search', params.search);
  if (params.module) query.append('module', params.module);
  if (params.is_system !== undefined && params.is_system !== null) query.append('is_system', params.is_system);
  if (params.sort_by) query.append('sort_by', params.sort_by);
  if (params.sort_order) query.append('sort_order', params.sort_order);

  const endpoint = `/users/permissions${query.toString() ? '?' + query.toString() : ''}`;
  return adminApi.get(endpoint);
}

export async function createPermission(permissionData) {
  return adminApi.post('/users/permissions', permissionData);
}

export async function getPermission(permissionId) {
  return adminApi.get(`/users/permissions/${permissionId}`);
}

export async function updatePermission(permissionId, updates) {
  return adminApi.patch(`/users/permissions/${permissionId}`, updates);
}

export async function deletePermission(permissionId) {
  return adminApi.delete(`/users/permissions/${permissionId}`);
}

export { adminApi, ApiError };