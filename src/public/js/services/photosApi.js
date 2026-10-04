import { ApiClient } from './api.js';

const photosApi = new ApiClient('/photos');

function buildQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value));
    }
  });
  return query.toString();
}

// --------------------------------- Photos

export async function listPhotos(params = {}) {
  const qs = buildQuery(params);
  return photosApi.get(qs ? `?${qs}` : '');
}

export async function searchPhotos(q, params = {}) {
  const qs = buildQuery({ ...params, q });
  return photosApi.get(`/search?${qs}`);
}

export async function getPhoto(id) {
  return photosApi.get(`/${id}`);
}

export async function updatePhoto(id, data) {
  return photosApi.patch(`/${id}`, data);
}

export async function deletePhoto(id) {
  return photosApi.delete(`/${id}`);
}

export async function restorePhoto(id) {
  return photosApi.post(`/${id}/restore`);
}

export function photoFileUrl(id, size = 'small', params = {}) {
  const qs = buildQuery({ size, ...params });
  return `/photos/${id}/file?${qs}`;
}

export async function uploadPhotos(files) {
  const form = new FormData();
  Array.from(files).forEach((file) => form.append('files', file));
  return photosApi.post('/upload', form);
}

export async function listDuplicates() {
  return photosApi.get('/duplicates');
}

// --------------------------------- Albums

export async function listAlbums(params = {}) {
  const qs = buildQuery(params);
  return photosApi.get(`/albums?${qs}`);
}

export async function getAlbum(id) {
  return photosApi.get(`/albums/${id}`);
}

export async function createAlbum(data) {
  return photosApi.post('/albums', data);
}

export async function updateAlbum(id, data) {
  return photosApi.patch(`/albums/${id}`, data);
}

export async function deleteAlbum(id) {
  return photosApi.delete(`/albums/${id}`);
}

export async function addAlbumPhotos(albumId, photoIds) {
  return photosApi.post(`/albums/${albumId}/photos`, { photo_ids: photoIds });
}

export async function removeAlbumPhoto(albumId, photoId) {
  return photosApi.delete(`/albums/${albumId}/photos/${photoId}`);
}

// --------------------------------- Personnes / visages

export async function listPeople() {
  return photosApi.get('/people');
}

export async function createPerson(name) {
  return photosApi.post('/people', { name });
}

export async function updatePerson(id, name) {
  return photosApi.patch(`/people/${id}`, { name });
}

export async function deletePerson(id) {
  return photosApi.delete(`/people/${id}`);
}

export async function assignFace(faceId, personId) {
  return photosApi.patch(`/faces/${faceId}`, { person_id: personId });
}

export async function unassignFace(faceId) {
  return photosApi.post(`/faces/${faceId}/unassign`);
}

export function faceCropUrl(faceId, size = 'small') {
  const qs = buildQuery({ size });
  return `/photos/faces/${faceId}/crop?${qs}`;
}

export async function listPersonFaces(personId) {
  return photosApi.get(`/people/${personId}/faces`);
}

export async function mergePeople(targetId, sourceId) {
  return photosApi.post(`/people/${targetId}/merge`, { person_id: sourceId });
}

export async function setPersonCover(personId, faceId) {
  return photosApi.patch(`/people/${personId}`, { cover_face_id: faceId });
}

// --------------------------------- Tags / lieux / jobs

export async function listTags() {
  return photosApi.get('/tags');
}

export async function listPlaces() {
  return photosApi.get('/places');
}

export async function listJobs() {
  return photosApi.get('/jobs');
}

export async function addPhotoTag(photoId, name) {
  return photosApi.post(`/${photoId}/tags`, { name });
}

export async function removePhotoTag(photoId, tagId) {
  return photosApi.delete(`/${photoId}/tags/${tagId}`);
}

// --------------------------------- Analyse

export async function analyzePhoto(photoId) {
  return photosApi.post(`/${photoId}/analyze`);
}

export async function getPhotoAnalysis(photoId) {
  return photosApi.get(`/${photoId}/analysis`);
}

// --------------------------------- Embeddings / similaires

export async function similarPhotos(photoId, limit = 12) {
  const qs = buildQuery({ limit });
  return photosApi.get(`/${photoId}/similar?${qs}`);
}

export async function reindexPhoto(photoId) {
  return photosApi.post(`/${photoId}/embeddings`);
}

export async function reindexFaces(photoId) {
  return photosApi.post(`/${photoId}/faces`);
}

// --------------------------------- Retouche

export async function listEdits(photoId) {
  return photosApi.get(`/${photoId}/edits`);
}

export async function createEdit(photoId, data) {
  return photosApi.post(`/${photoId}/edits`, data);
}

export function editFileUrl(photoId, editId) {
  return `/photos/${photoId}/edits/${editId}/file`;
}

export async function revertPhoto(photoId) {
  return photosApi.post(`/${photoId}/revert`);
}

// --------------------------------- Stockage (V3)

export async function getStorageStatus() {
  return photosApi.get('/storage/status');
}

export async function startStorageScan() {
  return photosApi.post('/import/scan');
}

export async function rebuildThumbnails(limit = 200) {
  const qs = buildQuery({ limit });
  return photosApi.post(`/thumbnails/rebuild?${qs}`);
}
