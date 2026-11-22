/**
 * PublisherMediaPicker — Sélection unifiée des médias
 * Sources : Bibliothèque Photos, Activités Garmin, Upload direct
 * Interface inspirée Instagram : grille, sélection multiple, drag-drop réorganisation
 */

import { publisherStore } from '../stores/publisherStore.js';
import { listPhotos, uploadPhotos, searchPhotos, listAlbums } from '../services/photosApi.js?v=8';
import { listSportActivities, getSuggestedPhotos } from '../services/sportApi.js?v=16';

const VIEW_MODES = {
  library: 'Bibliothèque',
  albums: 'Albums',
  garmin: 'Activités Garmin',
  upload: 'Importer',
};

export class PublisherMediaPicker {
  constructor(options = {}) {
    this.onSelectionChange = options.onSelectionChange || (() => {});
    this.onComplete = options.onComplete || (() => {});
    this.onCancel = options.onCancel || (() => {});
    this.multiSelect = options.multiSelect !== false;
    this.maxSelection = options.maxSelection || 10;
    this.allowedTypes = options.allowedTypes || ['photo', 'video'];
    this.element = null;
    this.view = 'library'; // 'library' | 'garmin' | 'upload'
    this.photos = [];
    this.cursor = null;
    this.hasMore = true;
    this.loading = false;
    this.currentAlbumId = null;
    this.searchQuery = '';
    this.garminActivities = [];
    this.selectedIds = new Set();
    this.dragItem = null;
    this.uploadQueue = [];
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = 'publisher-media-picker';
    this.element.innerHTML = this._render();
    host.appendChild(this.element);

    this._bindEvents();
    this._subscribeStore();
    this._loadInitial();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      this.selectedIds = new Set(state.draft.media.map(m => m.id));
      this._updateSelectionUI();
      this._updateCounter();
    });
  }

  _render() {
    return `
      <div class="pmp-header">
        <div class="pmp-header-left">
          <button type="button" class="pmp-btn pmp-btn-back" data-action="cancel">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
            </svg>
          </button>
        </div>
        <h2 class="pmp-header-title">Sélectionner des médias</h2>
        <div class="pmp-header-right">
          <div class="pmp-counter" data-counter>${publisherStore.draft.media.length} / ${this.maxSelection}</div>
          <button type="button" class="pmp-btn pmp-btn-primary" data-action="complete" disabled>
            Suivant
          </button>
        </div>
      </div>

      <div class="pmp-tabs" role="tablist">
        ${Object.entries(VIEW_MODES).map(([key, label]) => `
          <button type="button" role="tab" class="pmp-tab ${key === this.view ? 'active' : ''}" data-view="${key}" aria-selected="${key === this.view}">
            ${label}
          </button>
        `).join('')}
      </div>

      <div class="pmp-panels">
        <!-- Bibliothèque Photos -->
        <div class="pmp-panel ${this.view === 'library' ? 'active' : ''}" role="tabpanel" data-panel="library">
          <div class="pmp-preview" data-preview hidden>
            <div class="pmp-preview-stage" data-preview-stage>
              <img class="pmp-preview-img" src="" alt="">
              <span class="pmp-video-badge">▶</span>
              <button type="button" class="pmp-preview-remove" data-action="preview-remove" data-media-id="">✕</button>
            </div>
          </div>
          <div class="pmp-search">
            <input type="search" class="form-control" placeholder="Rechercher dans la bibliothèque…" data-search>
            <button type="button" class="pmp-btn pmp-btn-filter" data-action="filter-date" title="Filtrer par date">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
            </button>
          </div>
          <div class="pmp-grid" data-grid></div>
          <div class="pmp-load-more" data-load-more hidden>
            <button type="button" class="pmp-btn pmp-btn-secondary">Charger plus</button>
          </div>
          <div class="pmp-empty" data-empty hidden>Aucune photo trouvée</div>
        </div>

        <!-- Albums -->
        <div class="pmp-panel ${this.view === 'albums' ? 'active' : ''}" role="tabpanel" data-panel="albums">
          <div class="pmp-albums" data-albums-list></div>
        </div>

        <!-- Activités Garmin -->
        <div class="pmp-panel ${this.view === 'garmin' ? 'active' : ''}" role="tabpanel" data-panel="garmin">
          <div class="pmp-garmin-list" data-garmin-list></div>
          <div class="pmp-empty" data-garmin-empty hidden>Aucune activité Garmin</div>
        </div>

        <!-- Upload -->
        <div class="pmp-panel ${this.view === 'upload' ? 'active' : ''}" role="tabpanel" data-panel="upload">
          <div class="pmp-upload-dropzone" data-dropzone>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p>Glissez-déposez vos fichiers ici</p>
            <p class="pmp-upload-hint">ou cliquez pour parcourir</p>
            <input type="file" class="pmp-upload-input" multiple accept="image/*,video/*" data-upload-input hidden>
            <button type="button" class="pmp-btn pmp-btn-secondary" data-action="browse">Parcourir</button>
          </div>
          <div class="pmp-upload-queue" data-upload-queue></div>
        </div>
      </div>

      <!-- Barre de sélection active -->
      <div class="pmp-selected-bar" data-selected-bar hidden>
        <div class="pmp-selected-preview" data-selected-preview></div>
        <div class="pmp-selected-actions">
          <span class="pmp-selected-count" data-selected-count></span>
          <button type="button" class="pmp-btn pmp-btn-secondary" data-action="clear-selection">Tout désélectionner</button>
          <button type="button" class="pmp-btn pmp-btn-primary" data-action="confirm-selection">Confirmer la sélection</button>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    // Navigation
    this.element.querySelector('[data-action="cancel"]').addEventListener('click', () => this.onCancel());
    this.element.querySelector('[data-action="complete"]').addEventListener('click', () => this.onComplete());

    // Onglets
    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.addEventListener('click', () => this._switchView(btn.dataset.view));
    });

    // Recherche
    const searchInput = this.element.querySelector('[data-search]');
    let searchDebounce;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        this.searchQuery = e.target.value;
        this._loadLibrary();
      }, 300);
    });

    // Grille bibliothèque
    this.element.querySelector('[data-grid]').addEventListener('click', (e) => {
      const item = e.target.closest('[data-photo-id]');
      if (item) this._toggleSelection(item.dataset.photoId, item);
    });

    // Drag-drop réorganisation (sur la barre de sélection)
    this._setupDragDrop();

    // Charger plus
    this.element.querySelector('[data-load-more]').addEventListener('click', () => this._loadLibrary());

    // Garmin activités
    this.element.querySelector('[data-garmin-list]').addEventListener('click', (e) => {
      const act = e.target.closest('[data-activity-id]');
      if (act) this._openGarminActivity(act.dataset.activityId);
    });

    // Upload
    this.element.querySelector('[data-action="browse"]').addEventListener('click', () => {
      this.element.querySelector('[data-upload-input]').click();
    });
    this.element.querySelector('[data-upload-input]').addEventListener('change', (e) => {
      this._handleFiles(Array.from(e.target.files));
      e.target.value = '';
    });
    const dropzone = this.element.querySelector('[data-dropzone]');
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('drag-over'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      this._handleFiles(Array.from(e.dataTransfer.files));
    });

    // Actions sélection
    this.element.querySelector('[data-action="clear-selection"]').addEventListener('click', () => this._clearSelection());
    this.element.querySelector('[data-action="confirm-selection"]').addEventListener('click', () => this.onComplete());

    // Retrait via le grand aperçu (délégation)
    this.element.addEventListener('click', (e) => {
      const removeBtn = e.target.closest('[data-action="preview-remove"]');
      if (removeBtn) { this._removeSelectedMedia(removeBtn.dataset.mediaId); }
    });
  }

  _setupDragDrop() {
    const preview = this.element.querySelector('[data-selected-preview]');
    preview.addEventListener('dragstart', (e) => {
      const item = e.target.closest('[data-media-id]');
      if (item) {
        this.dragItem = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      }
    });
    preview.addEventListener('dragend', () => {
      if (this.dragItem) this.dragItem.classList.remove('dragging');
      this.dragItem = null;
    });
    preview.addEventListener('dragover', (e) => {
      e.preventDefault();
      const after = this._getDragAfterElement(preview, e.clientX);
      const draggable = document.querySelector('.dragging');
      if (after == null) preview.appendChild(draggable);
      else preview.insertBefore(draggable, after);
    });
    preview.addEventListener('drop', (e) => {
      e.preventDefault();
      this._reorderFromDOM();
    });
  }

  _getDragAfterElement(container, x) {
    const elements = [...container.querySelectorAll('[data-media-id]:not(.dragging)')];
    return elements.reduce((closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = x - box.left - box.width / 2;
      if (offset < 0 && offset > closest.offset) return { offset, element: child };
      return closest;
    }, { offset: Number.NEGATIVE_INFINITY }).element;
  }

  _reorderFromDOM() {
    const preview = this.element.querySelector('[data-selected-preview]');
    const newOrder = [...preview.querySelectorAll('[data-media-id]')].map(el => el.dataset.mediaId);
    const media = publisherStore.draft.media;
    const reordered = newOrder.map(id => media.find(m => m.id === id)).filter(Boolean);
    // Ajouter les médias non trouvés (au cas où)
    media.forEach(m => { if (!newOrder.includes(m.id)) reordered.push(m); });
    publisherStore.draft.media = reordered;
    publisherStore._notify();
  }

  _switchView(view) {
    this.view = view;
    this._syncTabs();
    if (view === 'library') this._loadLibrary();
    if (view === 'albums') this._loadAlbums();
    if (view === 'garmin') this._loadGarmin();
  }

  _syncTabs() {
    this.element.querySelectorAll('[data-view]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === this.view);
      btn.setAttribute('aria-selected', btn.dataset.view === this.view);
    });
    this.element.querySelectorAll('[data-panel]').forEach(panel => {
      panel.classList.toggle('active', panel.dataset.panel === this.view);
    });
  }

  async _loadInitial() {
    await this._loadLibrary();
    // Pré-sélectionner les médias déjà dans le store
    this.selectedIds = new Set(publisherStore.draft.media.map(m => m.id));
    this._updateSelectionUI();
    this._updateCounter();
  }

  async _loadLibrary(loadParams = {}) {
    if (this.loading) return;
    this.loading = true;
    this.element.querySelector('[data-grid]').classList.add('loading');

    try {
      const params = { page_size: 60 };
      if (this.currentAlbumId) params.album_id = this.currentAlbumId;
      if (loadParams.album_id) params.album_id = loadParams.album_id;
      if (this.cursor) params.cursor = this.cursor;
      if (this.searchQuery) params.search = this.searchQuery;

      const res = await listPhotos(params);
      const newPhotos = res.items || [];

      if (!this.cursor) this.photos = [];
      this.photos.push(...newPhotos);
      this.cursor = res.next_cursor || null;
      this.hasMore = !!this.cursor;

      this._renderLibrary();
    } catch (error) {
      console.error('[MediaPicker] Erreur chargement photos:', error);
    } finally {
      this.loading = false;
      this.element.querySelector('[data-grid]').classList.remove('loading');
      this.element.querySelector('[data-load-more]').hidden = !this.hasMore;
      this.element.querySelector('[data-empty]').hidden = this.photos.length > 0;
    }
  }

  _renderLibrary() {
    const grid = this.element.querySelector('[data-grid]');
    grid.innerHTML = this.photos.map(p => {
      const selected = this.selectedIds.has(p.id);
      const isVideo = p.mime_type?.startsWith('video/');
      return `
        <button type="button" class="pmp-media-item ${selected ? 'selected' : ''}" data-photo-id="${p.id}" data-media-type="${isVideo ? 'video' : 'photo'}">
          <img src="${p.thumbnail_url || `/photos/${p.id}/file?size=small`}" alt="${this._esc(p.title || '')}" loading="lazy">
          ${isVideo ? '<span class="pmp-video-badge">▶</span>' : ''}
          ${selected ? '<span class="pmp-check"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></span>' : ''}
          <span class="pmp-order" data-order></span>
        </button>
      `;
    }).join('');

    this._updateOrderBadges();
  }

  async _loadAlbums() {
    const container = this.element.querySelector('[data-albums-list]');
    if (!container) return;
    container.innerHTML = '<div class="pmp-loading">Chargement des albums…</div>';
    try {
      const res = await listAlbums({ page_size: 50 });
      const albums = res.items || [];
      container.innerHTML = albums.length
        ? albums.map(a => `
          <button type="button" class="pmp-album-item" data-album-id="${a.id}">
            <span class="pmp-album-cover">${a.cover_photo_id ? `<img src="/photos/${a.cover_photo_id}/file?size=small" alt="">` : '<span class="pmp-album-placeholder">📷</span>'}</span>
            <span class="pmp-album-info"><strong>${this._esc(a.name)}</strong><span>${a.photo_count || 0} photo(s)</span></span>
          </button>
        `).join('')
        : '<div class="pmp-empty">Aucun album pour le moment.</div>';
      container.querySelectorAll('[data-album-id]').forEach(btn => {
        btn.addEventListener('click', () => this._openAlbum(btn.dataset.albumId));
      });
    } catch (error) {
      console.error('[MediaPicker] Erreur chargement albums:', error);
      container.innerHTML = '<div class="pmp-empty">Erreur chargement des albums.</div>';
    }
  }

  async _openAlbum(albumId) {
    this.currentAlbumId = albumId;
    this.view = 'library';
    this._syncTabs();
    await this._loadLibrary({ album_id: albumId });
  }

  async _loadGarmin() {
    const container = this.element.querySelector('[data-garmin-list]');
    container.innerHTML = '<div class="loading">Chargement des activités…</div>';

    try {
      const res = await listSportActivities({ page_size: 20 });
      const activities = res.items || [];

      container.innerHTML = activities.map(a => `
        <button type="button" class="pmp-garmin-item" data-activity-id="${a.id}">
          <div class="pmp-garmin-info">
            <strong>${this._esc(a.activity_name || a.sport_type || 'Activité')}</strong>
            <span>${new Date(a.started_at).toLocaleDateString('fr-FR')} • ${a.distance_m ? (a.distance_m/1000).toFixed(1)+' km' : ''} ${a.elevation_gain_m ? '• D+' + Math.round(a.elevation_gain_m) + 'm' : ''}</span>
          </div>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      `).join('') || '<div class="pmp-empty">Aucune activité Garmin</div>';

      this.element.querySelector('[data-garmin-empty]').hidden = activities.length > 0;
    } catch (error) {
      container.innerHTML = '<div class="pmp-empty">Erreur chargement Garmin</div>';
    }
  }

  async _openGarminActivity(activityId) {
    try {
      const res = await getSuggestedPhotos(null, 50); // Besoin d'un publication_id pour l'API actuelle
      // Pour l'instant, on redirige vers l'activité
      this._notifyGarminSelection(activityId);
    } catch (error) {
      console.error('[MediaPicker] Erreur photos Garmin:', error);
    }
  }

  _notifyGarminSelection(activityId) {
    // Émettre un événement pour que le parent charge les photos de l'activité
    this.element.dispatchEvent(new CustomEvent('pmp:garmin-select', {
      detail: { activityId },
      bubbles: true,
    }));
  }

  _handleFiles(files) {
    const validFiles = files.filter(f => this.allowedTypes.some(t => f.type.startsWith(t)));
    if (validFiles.length === 0) return;

    this.uploadQueue.push(...validFiles.map(f => ({ file: f, id: `upload_${Date.now()}_${Math.random()}`, progress: 0 })));
    this._renderUploadQueue();
    this._processUploadQueue();
  }

  async _processUploadQueue() {
    for (const item of this.uploadQueue) {
      if (item.progress > 0) continue; // Déjà en cours
      try {
        item.progress = 10;
        this._renderUploadQueue();
        const formData = new FormData();
        formData.append('file', item.file);
        const res = await uploadPhotos(formData);
        item.progress = 100;
        if (res.items?.[0]) {
          // Ajouter à la sélection automatiquement
          const photo = res.items[0];
          publisherStore.addMedia([{
            id: photo.id,
            url: `/photos/${photo.id}/file`,
            thumbnail_url: photo.thumbnail_url,
            crop: { x: 0, y: 0, w: 1, h: 1 },
            type: photo.mime_type?.startsWith('video/') ? 'video' : 'photo',
            source: 'upload',
          }]);
        }
      } catch (error) {
        item.error = error?.message || 'Échec upload';
        console.error('[MediaPicker] Upload failed:', error);
      }
      this._renderUploadQueue();
    }
  }

  _renderUploadQueue() {
    const queue = this.element.querySelector('[data-upload-queue]');
    queue.innerHTML = this.uploadQueue.map(item => `
      <div class="pmp-upload-item ${item.error ? 'error' : ''} ${item.progress === 100 ? 'done' : ''}">
        <div class="pmp-upload-info">
          <span class="pmp-upload-name">${this._esc(item.file.name)}</span>
          <div class="pmp-upload-bar"><div class="pmp-upload-fill" style="width:${item.progress}%"></div></div>
        </div>
        ${item.error ? `<span class="pmp-upload-error">${this._esc(item.error)}</span>` : ''}
      </div>
    `).join('');
  }

  _toggleSelection(mediaId, itemEl) {
    if (this.selectedIds.has(mediaId)) {
      this.selectedIds.delete(mediaId);
      itemEl.classList.remove('selected');
      publisherStore.removeMedia(mediaId);
    } else {
      if (this.selectedIds.size >= this.maxSelection) return;
      this.selectedIds.add(mediaId);
      itemEl.classList.add('selected');
      const photo = this.photos.find(p => p.id === mediaId);
      if (photo) {
        publisherStore.addMedia([{
          id: photo.id,
          url: photo.file_url,
          thumbnail_url: photo.thumbnail_url,
          type: photo.mime_type?.startsWith('video/') ? 'video' : 'photo',
          source: 'library',
        }]);
      }
    }
    this._updateSelectionUI();
    this._updateCounter();
    this._updateOrderBadges();
  }

  _updatePreview() {
    const previewPanel = this.element.querySelector('[data-preview]');
    if (!previewPanel) return;
    if (this.selectedIds.size === 0) { previewPanel.hidden = true; return; }
    const mediaMap = new Map(publisherStore.draft.media.map(m => [m.id, m]));
    const firstId = [...this.selectedIds].find(id => mediaMap.has(id));
    const media = firstId ? mediaMap.get(firstId) : null;
    const stage = previewPanel.querySelector('[data-preview-stage]');
    if (!stage || !media) { previewPanel.hidden = true; return; }
    stage.innerHTML = `
      <img class="pmp-preview-img" src="${media.thumbnail_url || media.url}" alt="">
      ${media.type === 'video' ? '<span class="pmp-video-badge">▶</span>' : ''}
      <button type="button" class="pmp-preview-remove" data-action="preview-remove" data-media-id="${media.id}">✕</button>
    `;
    previewPanel.hidden = false;
  }

  _removeSelectedMedia(mediaId) {
    this.selectedIds.delete(mediaId);
    publisherStore.removeMedia(mediaId);
    this._updateSelectionUI();
    this._updateCounter();
    this._updateGridSelection();
  }

  _updateSelectionUI() {
    const preview = this.element.querySelector('[data-selected-preview]');
    const bar = this.element.querySelector('[data-selected-bar]');
    const completeBtn = this.element.querySelector('[data-action="complete"]');
    const previewPanel = this.element.querySelector('[data-preview]');

    if (this.selectedIds.size === 0) {
      if (bar) bar.hidden = true;
      if (completeBtn) completeBtn.disabled = true;
      if (previewPanel) previewPanel.hidden = true;
      return;
    }

    if (bar) bar.hidden = false;
    if (completeBtn) completeBtn.disabled = false;
    if (previewPanel) this._updatePreview();

    const mediaMap = new Map(publisherStore.draft.media.map(m => [m.id, m]));
    preview.innerHTML = [...this.selectedIds].map(id => {
      const media = mediaMap.get(id);
      if (!media) return '';
      return `
        <div class="pmp-selected-item" data-media-id="${id}" draggable="true">
          <img src="${media.thumbnail_url}" alt="">
          <button type="button" class="pmp-selected-remove" data-remove="${id}" aria-label="Retirer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      `;
    }).join('');

    // Bind remove buttons
    preview.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._removeSelectedMedia(btn.dataset.remove);
      });
    });
  }

  _updateGridSelection() {
    this.element.querySelectorAll('[data-photo-id]').forEach(item => {
      item.classList.toggle('selected', this.selectedIds.has(item.dataset.photoId));
    });
    this._updateOrderBadges();
  }

  _updateOrderBadges() {
    const orderMap = new Map();
    publisherStore.draft.media.forEach((m, i) => orderMap.set(m.id, i + 1));

    this.element.querySelectorAll('[data-photo-id]').forEach(item => {
      const orderEl = item.querySelector('[data-order]');
      const order = orderMap.get(item.dataset.photoId);
      if (orderEl) {
        orderEl.textContent = order || '';
        orderEl.style.display = order ? 'flex' : 'none';
      }
    });

    this.element.querySelectorAll('[data-selected-preview] .pmp-selected-item').forEach((el, i) => {
      // L'ordre dans la preview suit l'ordre du store
    });
  }

  _updateCounter() {
    const counter = this.element.querySelector('[data-counter]');
    if (counter) counter.textContent = `${publisherStore.draft.media.length} / ${this.maxSelection}`;

    const selectedCounter = this.element.querySelector('[data-selected-count]');
    if (selectedCounter) selectedCounter.textContent = `${this.selectedIds.size} sélectionné${this.selectedIds.size > 1 ? 's' : ''}`;
  }

  _clearSelection() {
    this.selectedIds.clear();
    publisherStore.draft.media = [];
    publisherStore._notify();
    this._updateGridSelection();
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&', '<': '<', '>': '>', '"': '"', "'": "'" }[c]));
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createPublisherMediaPicker(options) {
  return new PublisherMediaPicker(options);
}