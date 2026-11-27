/**
 * PublisherMediaPicker — Sélection unifiée des médias
 * Sources : Bibliothèque Photos, Activités Garmin, Upload direct
 * Interface inspirée Instagram : grille, sélection multiple,
 * bande de sélection réordonnable, drag-drop
 */

import { publisherStore } from '../stores/publisherStore.js';
import { listPhotos, uploadPhotos, listAlbums } from '../services/photosApi.js?v=8';
import { listSportActivities, getSuggestedPhotos, getSuggestedPhotosForActivity } from '../services/sportApi.js?v=16';

const VIEW_MODES = {
  library: { label: 'Bibliothèque', short: 'Photos' },
  albums: { label: 'Albums', short: 'Albums' },
  garmin: { label: 'Activités Garmin', short: 'Garmin' },
  upload: { label: 'Importer', short: 'Importer' },
};

export class PublisherMediaPicker {
  constructor(options = {}) {
    this.onSelectionChange = options.onSelectionChange || (() => {});
    this.onComplete = options.onComplete || (() => {});
    this.onCancel = options.onCancel || (() => {});
    this.multiSelect = options.multiSelect !== false;
    this.maxSelection = options.maxSelection || 10;
    this.minSelection = options.minSelection || 1;
    this.allowedTypes = options.allowedTypes || ['photo', 'video'];
    this.format = options.format || 'post';
    // Le type de publication se choisit AVANT les photos : il conditionne
    // le nombre maximal de médias et les types autorisés.
    this.formats = options.formats || null;
    this.canSwitchFormat = !!(options.formats && options.canSwitchFormat !== false);
    this.onFormatChange = options.onFormatChange || (() => {});
    this.element = null;
    this.view = 'library'; // 'library' | 'albums' | 'garmin' | 'upload'
    this.photos = [];
    this.cursor = null;
    this.hasMore = true;
    this.loading = false;
    this.currentAlbumId = null;
    this.searchQuery = '';
    this.garminActivities = [];
    this.selectedIds = new Set();
    this.previewMediaId = null;
    this.dragItem = null;
    this.uploadQueue = [];
    this.notice = '';
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = `publisher-media-picker publisher-media-picker--${this.format}`;
    this.element.innerHTML = this._render();
    host.appendChild(this.element);

    this._bindEvents();
    this._subscribeStore();
    this._loadInitial();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      // Les ids du store sont normalisés en chaînes (voir publisherStore.addMedia)
      this.selectedIds = new Set((state.draft.media || []).map(m => String(m.id)));
      this._updateSelectionUI();
      this._updateCounter();
      this._updateGridSelection();
    });
  }

  /** Type Instagram d'un fichier : MIME réel, avec repli sur l'extension. */
  _fileKind(file) {
    const type = String(file?.type || '').toLowerCase();
    if (type.startsWith('image/')) return 'photo';
    if (type.startsWith('video/')) return 'video';
    const name = String(file?.name || '').toLowerCase();
    if (/\.(jpe?g|png|webp|gif|heic|heif|avif)$/.test(name)) return 'photo';
    if (/\.(mp4|mov|m4v|webm)$/.test(name)) return 'video';
    return null;
  }

  _allowedFile(file) {
    const kind = this._fileKind(file);
    return !!kind && this.allowedTypes.includes(kind);
  }

  _setNotice(message) {
    this.notice = message || '';
    const el = this.element?.querySelector?.('[data-notice]');
    if (!el) return;
    el.textContent = this.notice;
    el.hidden = !this.notice;
  }

  _toggleFormatMenu(force) {
    const btn = this.element?.querySelector('[data-action="select-format"]');
    const menu = this.element?.querySelector('[data-format-menu]');
    if (!btn || !menu) return;
    const open = force !== undefined ? force : menu.hidden;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  }

  _render() {
    return `
      <div class="pmp-header">
        <button type="button" class="pmp-btn pmp-btn-back" data-action="cancel" aria-label="Retour">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
          </svg>
        </button>
        <div class="pmp-header-title ${this.canSwitchFormat ? 'pmp-header-title--format' : ''}">
          ${this._renderFormatSelector()}
          <span class="pmp-counter" data-counter>0 / ${this.maxSelection}</span>
        </div>
        <button type="button" class="pmp-btn pmp-btn-primary" data-action="complete" disabled>
          Suivant
        </button>
      </div>

      <div class="pmp-tabs" role="tablist">
        ${Object.entries(VIEW_MODES).map(([key, mode]) => `
          <button type="button" role="tab" class="pmp-tab ${key === this.view ? 'active' : ''}" data-view="${key}"
                  aria-selected="${key === this.view}" title="${mode.label}">
            ${mode.short}
          </button>
        `).join('')}
      </div>
      <div class="pmp-notice" data-notice role="status" aria-live="polite" hidden></div>

      <div class="pmp-body">
        <div class="pmp-panels">
          <!-- Bibliothèque Photos -->
          <div class="pmp-panel ${this.view === 'library' ? 'active' : ''}" role="tabpanel" data-panel="library">
            <div class="pmp-preview" data-selection-preview hidden>
              <div class="pmp-preview-stage" data-preview-stage></div>
              <div class="pmp-preview-meta"><span data-preview-position></span><span>Appuyez pour sélectionner</span></div>
            </div>
            <div class="pmp-search">
              <input type="search" class="form-control" placeholder="Rechercher…" data-search aria-label="Rechercher dans la bibliothèque">
              <button type="button" class="pmp-btn pmp-btn-filter" data-action="filter-date" title="Filtrer par date" aria-label="Filtrer par date">
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

        <!-- Bande de sélection (ordre = ordre de publication) -->
        <div class="pmp-selected-bar" data-selected-bar hidden>
          <div class="pmp-selection-head">
            <span class="pmp-selected-count" data-selected-count></span>
            <button type="button" class="pmp-btn pmp-btn-ghost pmp-btn-sm" data-action="clear-selection">Tout effacer</button>
          </div>
          <div class="pmp-selected-preview" data-selected-preview></div>
        </div>
      </div>
    `;
  }

  /**
   * Sélecteur de format dans le header du picker : le choix du type de
   * publication (Publication, Carrousel, Reel, Story) précède et conditionne
   * la sélection des photos.
   */
  _renderFormatSelector() {
    if (!this.canSwitchFormat) return '<h2>Nouvelle publication</h2>';
    const config = this.formats[this.format] || this.formats.post;
    return `
      <div class="publisher-format pmp-format" data-format-root>
        <button type="button" class="publisher-format-btn pmp-format-btn" data-action="select-format" aria-haspopup="menu" aria-expanded="false" title="Choisir le type de publication">
          <span class="publisher-format-icon">${config.icon}</span>
          <span class="publisher-format-label">${config.label}</span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div class="publisher-format-menu" data-format-menu hidden role="menu">
          ${Object.entries(this.formats).map(([key, c]) => `
            <button type="button" role="menuitem" class="publisher-format-option ${key === this.format ? 'active' : ''}" data-format="${key}">
              <span class="publisher-format-icon">${c.icon}</span>
              <span>${c.label}</span>
            </button>
          `).join('')}
        </div>
      </div>
    `;
  }

  _bindEvents() {
    // Sélecteur de format : le type de publication conditionne la sélection
    const formatBtn = this.element.querySelector('[data-action="select-format"]');
    if (formatBtn) {
      formatBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._toggleFormatMenu();
      });
      this.element.querySelectorAll('[data-format]').forEach(opt => {
        opt.addEventListener('click', () => {
          this._toggleFormatMenu(false);
          const format = opt.dataset.format;
          if (format && format !== this.format) this.onFormatChange(format);
        });
      });
      this.element.addEventListener('click', () => this._toggleFormatMenu(false));
    }

    // Navigation
    this.element.querySelector('[data-action="cancel"]').addEventListener('click', () => this.onCancel());
    this.element.querySelector('[data-action="complete"]').addEventListener('click', () => {
      if (this.selectedIds.size < this.minSelection) return;
      this.onComplete();
    });

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
        this.cursor = null;
        this._loadLibrary();
      }, 300);
    });

    // Grille bibliothèque
    this.element.querySelector('[data-grid]').addEventListener('click', (e) => {
      const item = e.target.closest('[data-photo-id]');
      if (item) this._toggleSelection(item.dataset.photoId, item);
    });

    // Drag-drop réorganisation (sur la bande de sélection)
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
      if (!draggable) return;
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
    const newOrder = [...preview.querySelectorAll('[data-media-id]')].map(el => String(el.dataset.mediaId));
    const media = publisherStore.draft.media;
    const reordered = newOrder.map(id => media.find(m => String(m.id) === id)).filter(Boolean);
    // Ajouter les médias non trouvés (au cas où)
    media.forEach(m => { if (!newOrder.includes(String(m.id))) reordered.push(m); });
    reordered.forEach((m, i) => { m.order = i; });
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
    this.selectedIds = new Set(publisherStore.draft.media.map(m => String(m.id)));
    this._updateSelectionUI();
    this._updateCounter();
    this._updateGridSelection();
  }

  /** Filtre les médias non autorisés pour le format courant (photo seule, photo+vidéo…). */
  _isAllowed(photo) {
    const isVideo = !!photo.mime_type?.startsWith('video/');
    return this.allowedTypes.includes(isVideo ? 'video' : 'photo');
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
      const visible = this.photos.filter(p => this._isAllowed(p));
      this.element.querySelector('[data-empty]').hidden = visible.length > 0;
    }
  }

  _renderLibrary() {
    const grid = this.element.querySelector('[data-grid]');
    const items = this.photos.filter(p => this._isAllowed(p));
    grid.innerHTML = items.map(p => {
      const id = String(p.id);
      const selected = this.selectedIds.has(id);
      const isVideo = p.mime_type?.startsWith('video/');
      return `
        <button type="button" class="pmp-media-item ${selected ? 'selected' : ''}" data-photo-id="${id}" data-media-type="${isVideo ? 'video' : 'photo'}" aria-pressed="${selected}">
          <img src="${p.thumbnail_url || `/photos/${p.id}/file?size=small`}" alt="${this._esc(p.title || '')}" loading="lazy">
          ${isVideo ? '<span class="pmp-video-badge">▶</span>' : ''}
          <span class="pmp-check" ${selected ? '' : 'hidden'}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></span>
          <span class="pmp-order" data-order hidden></span>
        </button>
      `;
    }).join('');

    this._updateGridSelection();
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
    this.cursor = null;
    this._syncTabs();
    await this._loadLibrary({ album_id: albumId });
  }

  async _loadGarmin() {
    const container = this.element.querySelector('[data-garmin-list]');
    container.innerHTML = '<div class="pmp-loading">Chargement des activités…</div>';

    try {
      const res = await listSportActivities({ page_size: 20 });
      const activities = res.items || [];

      // A03 : le message d'état vide est porté uniquement par
      // [data-garmin-empty] (template), pour éviter le doublon visuel.
      container.innerHTML = activities.map(a => `
        <button type="button" class="pmp-garmin-item" data-activity-id="${a.id}">
          <div class="pmp-garmin-info">
            <strong>${this._esc(a.activity_name || a.sport_type || 'Activité')}</strong>
            <span>${new Date(a.started_at).toLocaleDateString('fr-FR')} • ${a.distance_m ? (a.distance_m/1000).toFixed(1)+' km' : ''} ${a.elevation_gain_m ? '• D+' + Math.round(a.elevation_gain_m) + 'm' : ''}</span>
          </div>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      `).join('');

      const empty = this.element.querySelector?.('[data-garmin-empty]');
      if (empty) empty.hidden = activities.length > 0;
    } catch (error) {
      container.innerHTML = '';
      const empty = this.element.querySelector?.('[data-garmin-empty]');
      if (empty) empty.hidden = true;
      const detail = error?.data?.detail || error?.message || String(error);
      this._setNotice(`Chargement des activités Garmin impossible : ${detail}`);
    }
  }

  async _openGarminActivity(activityId) {
    try {
      // Lot 0 (A03) : suggestions Garmin réellement liées à l'activité.
      const photos = await getSuggestedPhotosForActivity(activityId, this.maxSelection);
      const items = Array.isArray(photos) ? photos : (photos?.items || []);
      const existing = new Set(publisherStore.draft.media.map(
        m => String(m.photoId ?? String(m.id).replace(/^photo_/, '')),
      ));
      const remaining = Math.max(0, this.maxSelection - publisherStore.draft.media.length);
      const toAdd = [];
      for (const p of (remaining > 0 ? items : [])) {
        const key = String(p.id);
        if (existing.has(key)) continue;
        existing.add(key);
        toAdd.push({
          id: p.id,
          photoId: p.id,
          url: `/photos/${p.id}/file`,
          thumbnail_url: p.thumbnail_url || `/photos/${p.id}/file?size=small`,
          type: 'photo',
          source: 'garmin',
        });
        if (toAdd.length >= remaining) break;
      }
      if (toAdd.length > 0) publisherStore.addMedia(toAdd);
      this._notifyGarminSelection(activityId);
    } catch (error) {
      const detail = error?.data?.detail || error?.message || String(error);
      console.error('[MediaPicker] Erreur photos Garmin:', detail);
      this._setNotice(`Suggestions Garmin indisponibles pour cette activité : ${detail}`);
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
    const allFiles = Array.from(files || []);
    if (!allFiles.length) return;

    const validFiles = allFiles.filter(f => this._allowedFile(f));
    if (validFiles.length === 0) {
      const accepted = this.allowedTypes.includes('video') ? 'images ou vidéos' : 'images';
      this._setNotice(`Seules les ${accepted} sont acceptées pour ce format.`);
      return;
    }

    // La limite s'applique aussi à l'import direct (bypass du toggle).
    const capacity = Math.max(0, this.maxSelection - (publisherStore.draft.media?.length || 0));
    if (!capacity) {
      this._setNotice(`Limite de ${this.maxSelection} médias atteinte pour ce format.`);
      return;
    }

    const acceptedFiles = validFiles.slice(0, capacity);
    const ignored = allFiles.length - acceptedFiles.length;
    this._setNotice(ignored > 0
      ? `${acceptedFiles.length} fichier(s) ajouté(s) · ${ignored} ignoré(s) (limite ${this.maxSelection}).`
      : '');

    this.uploadQueue.push(...acceptedFiles.map(f => ({ file: f, id: `upload_${Date.now()}_${Math.random()}`, progress: 0 })));
    this._renderUploadQueue();
    this._processUploadQueue();
  }

  async _processUploadQueue() {
    for (const item of this.uploadQueue) {
      if (item.progress > 0) continue; // Déjà en cours
      try {
        item.progress = 10;
        this._renderUploadQueue();
        const res = await uploadPhotos([item.file]);
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

  _toggleSelection(rawId, itemEl) {
    // Les dataset DOM sont toujours des chaînes : normaliser avant comparaison
    const mediaId = String(rawId);

    if (this.selectedIds.has(mediaId)) {
      this.selectedIds.delete(mediaId);
      if (itemEl) itemEl.classList.remove('selected');
      publisherStore.removeMedia(mediaId);
      this._setNotice('');
    } else {
      if (this.selectedIds.size >= this.maxSelection) {
        this._setNotice(`Limite de ${this.maxSelection} médias atteinte pour ce format.`);
        return;
      }
      const photo = this.photos.find(p => String(p.id) === mediaId);
      if (!photo) return;
      this.selectedIds.add(mediaId);
      if (itemEl) itemEl.classList.add('selected');
      publisherStore.addMedia([{
        id: photo.id,
        photoId: photo.id,
        url: photo.file_url || `/photos/${photo.id}/file`,
        thumbnail_url: photo.thumbnail_url || `/photos/${photo.id}/file?size=small`,
        type: photo.mime_type?.startsWith('video/') ? 'video' : 'photo',
        source: 'library',
      }]);
    }
    this._updateSelectionUI();
    this._updateCounter();
    this._updateGridSelection();
    this.onSelectionChange([...this.selectedIds]);
  }

  _removeSelectedMedia(mediaId) {
    const id = String(mediaId);
    this.selectedIds.delete(id);
    publisherStore.removeMedia(id);
    this._updateSelectionUI();
    this._updateCounter();
    this._updateGridSelection();
  }

  _updateSelectionUI() {
    const bar = this.element.querySelector('[data-selected-bar]');
    const preview = this.element.querySelector('[data-selected-preview]');
    const completeBtn = this.element.querySelector('[data-action="complete"]');
    const count = publisherStore.draft.media.length;

    if (completeBtn) completeBtn.disabled = count < this.minSelection;

    if (bar) bar.hidden = count === 0;
    if (!preview) return;
    if (count === 0) {
      preview.innerHTML = '';
      this.previewMediaId = null;
      this._renderActivePreview();
      return;
    }

    preview.innerHTML = publisherStore.draft.media.map((media, idx) => `
      <div class="pmp-selected-item" data-media-id="${String(media.id)}" data-preview-media="${String(media.id)}" draggable="true" role="button" tabindex="0" aria-label="Prévisualiser la photo ${idx + 1}">
        <img src="${media.thumbnail_url || media.url}" alt="">
        <span class="pmp-selected-index">${idx + 1}</span>
        <button type="button" class="pmp-selected-remove" data-remove="${String(media.id)}" aria-label="Retirer">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    `).join('');

    if (!publisherStore.draft.media.some(media => String(media.id) === String(this.previewMediaId))) {
      this.previewMediaId = publisherStore.draft.media[0] ? String(publisherStore.draft.media[0].id) : null;
    }
    this._renderActivePreview();

    // Bind remove buttons
    preview.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._removeSelectedMedia(btn.dataset.remove);
      });
    });
    preview.querySelectorAll('[data-preview-media]').forEach((item) => {
      const activate = (event) => {
        if (event.target.closest('[data-remove]')) return;
        this.previewMediaId = String(item.dataset.previewMedia);
        this._renderActivePreview();
      };
      item.addEventListener('click', activate);
      item.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(event); }
      });
    });
  }

  _renderActivePreview() {
    const selected = publisherStore.draft.media || [];
    const preview = this.element?.querySelector('[data-selection-preview]');
    const stage = this.element?.querySelector('[data-preview-stage]');
    const position = this.element?.querySelector('[data-preview-position]');
    if (!preview || !stage) return;
    preview.hidden = selected.length === 0;
    if (!selected.length) { stage.innerHTML = ''; return; }
    const index = selected.findIndex(media => String(media.id) === String(this.previewMediaId));
    const media = selected[Math.max(index, 0)];
    this.previewMediaId = String(media.id);
    stage.innerHTML = `
      <img class="pmp-preview-img" src="${this._esc(media.url || media.thumbnail_url || '')}" alt="Aperçu de la publication">
      <button type="button" class="pmp-preview-remove" data-preview-remove aria-label="Retirer ce média">×</button>
      ${media.type === 'video' ? '<span class="pmp-video-badge">Vidéo</span>' : ''}`;
    stage.querySelector('[data-preview-remove]').addEventListener('click', () => this._removeSelectedMedia(media.id));
    if (position) position.textContent = `${index + 1} / ${selected.length} · ${this.format === 'story' || this.format === 'reel' ? '9:16' : '4:5'}`;
    this.element.querySelectorAll('[data-preview-media]').forEach((item) => {
      item.classList.toggle('active', String(item.dataset.previewMedia) === this.previewMediaId);
    });
  }

  _updateGridSelection() {
    if (!this.element) return;
    const full = this.selectedIds.size >= this.maxSelection;
    this.element.querySelectorAll('[data-photo-id]').forEach(item => {
      const selected = this.selectedIds.has(String(item.dataset.photoId));
      item.classList.toggle('selected', selected);
      item.setAttribute('aria-pressed', String(selected));
      item.setAttribute('aria-disabled', String(full && !selected));
      const check = item.querySelector('.pmp-check');
      if (check) check.hidden = !selected;
    });
    this._updateOrderBadges();
  }

  _updateOrderBadges() {
    if (!this.element) return;
    const orderMap = new Map();
    publisherStore.draft.media.forEach((m, i) => orderMap.set(String(m.id), i + 1));

    this.element.querySelectorAll('[data-photo-id]').forEach(item => {
      const orderEl = item.querySelector('[data-order]');
      if (!orderEl) return;
      const order = orderMap.get(String(item.dataset.photoId));
      orderEl.textContent = order || '';
      orderEl.hidden = !order;
    });
  }

  _updateCounter() {
    if (!this.element) return;
    const counter = this.element.querySelector('[data-counter]');
    if (counter) counter.textContent = `${publisherStore.draft.media.length} / ${this.maxSelection}`;

    const selectedCounter = this.element.querySelector('[data-selected-count]');
    if (selectedCounter) {
      const n = publisherStore.draft.media.length;
      const min = this.minSelection;
      const suffix = min > 1 && n < min ? ` · minimum ${min}` : '';
      selectedCounter.textContent = `${n} sélectionné${n > 1 ? 's' : ''}${suffix}`;
    }
  }

  _clearSelection() {
    this.selectedIds.clear();
    publisherStore.draft.media = [];
    publisherStore._notify();
    this._setNotice('');
    this._updateGridSelection();
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createPublisherMediaPicker(options) {
  return new PublisherMediaPicker(options);
}
