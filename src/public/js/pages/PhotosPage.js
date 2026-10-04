import {
  addPhotoTag,
  analyzePhoto,
  createAlbum,
  createEdit,
  createPerson,
  deleteAlbum,
  deletePhoto,
  deletePerson,
  editFileUrl,
  faceCropUrl,
  getPhoto,
  getStorageStatus,
  listAlbums,
  listPeople,
  listPersonFaces,
  listPhotos,
  listPlaces,
  mergePeople,
  photoFileUrl,
  reindexFaces,
  removePhotoTag,
  reindexPhoto,
  rebuildThumbnails,
  revertPhoto,
  restorePhoto,
  searchPhotos,
  setPersonCover,
  startStorageScan,
  unassignFace,
  updateAlbum,
  updatePerson,
  updatePhoto,
  uploadPhotos,
} from '../services/photosApi.js?v=4';
import { authStore } from '../stores/auth.js';

const PAGE_SIZE = 60;

// Suggestions de « Recherche intelligente » (recherche en langage naturel).
const PHOTO_SEARCH_SUGGESTIONS = [
  'photos de montagne',
  'portrait',
  'nuit',
  'avec gps',
];

export class PhotosPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.view = 'all';
    this.photos = [];
    this.cursor = null;
    this.hasMore = true;
    this.loading = false;
    this.filter = null;
    this.searchQuery = '';
    this.albums = [];
    this.people = [];
    this.personFaces = [];
    this.places = [];
    this.detail = null;
    this.pollHandle = null;
    this.observer = null;
    this.lightboxImageNonce = 0;
  }

  // ------------------------------------------------------------- cycle de vie

  async initialize() {
    // Chargement initial différé : loadData() est appelé après render().
  }

  setView(view) {
    if (this.view === view && !this.filter && !this.searchQuery) return;
    this.view = view;
    this.filter = null;
    this.searchQuery = '';
    this.photos = [];
    this.cursor = null;
    this.hasMore = true;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content photos-page';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>${this._viewTitle()}</h1>
          <p class="page-subtitle">${this._viewSubtitle()}</p>
        </div>
        <div class="page-header-actions" data-header-actions></div>
      </div>

      <div class="photos-toolbar">
        <input type="search" class="form-control photos-search"
               placeholder="Rechercher (ex. « photos de montagne »)"
               data-search value="${this._esc(this.searchQuery)}">
        ${this.filter ? `
          <button type="button" class="btn btn-secondary" data-action="clear-filter">
            ${this._esc(this.filter.name)} ✕
          </button>` : ''}
        <span class="photos-count" data-count></span>
      </div>

      ${this._isGridView() ? `
      <div class="photos-smart" data-smart>
        <span class="photos-smart-label">Recherche intelligente</span>
        ${PHOTO_SEARCH_SUGGESTIONS.map((query) => `
          <button type="button" class="photos-smart-chip" data-smart-q="${this._esc(query)}">${this._esc(query)}</button>`).join('')}
      </div>` : ''}

      <div class="photos-faces-panel" data-faces-panel hidden></div>
      <div class="photos-storage-panel" data-storage-panel hidden></div>
      <div data-cards class="photos-cards"></div>
      <div class="photos-grid" data-grid></div>
      <div class="photos-sentinel" data-sentinel></div>
      <p class="empty-message" data-empty hidden>Aucune photo.</p>

      <div class="photos-lightbox" data-lightbox hidden>
        <div class="photos-lightbox-backdrop" data-action="close-lightbox"></div>
        <div class="photos-lightbox-panel" data-lightbox-panel>
          <button type="button" class="photos-lightbox-close" data-action="close-lightbox" aria-label="Fermer">✕</button>
          <div class="photos-lightbox-media" data-lightbox-media></div>
          <aside class="photos-lightbox-info" data-lightbox-info></aside>
        </div>
      </div>
    `;

    this._renderHeaderActions();
    this._bindToolbar();
    this._bindLightbox();
    return this.element;
  }

  async loadData() {
    this._stopPolling();
    try {
      if (this.view === 'albums') {
        await this._loadAlbums();
        this._renderCards();
      } else if (this.view === 'people') {
        await this._loadPeople();
        this._renderCards();
      } else if (this.view === 'places') {
        await this._loadPlaces();
        this._renderCards();
      }
      if (this.filter && this.filter.type === 'person') {
        await this._loadPersonFaces();
        this._renderFacesPanel();
      } else {
        this._hideFacesPanel();
      }
      if (this.view === 'all' || this.view === 'favorites' || this.filter) {
        await this._resetGrid();
      }
    } catch (error) {
      this._toast(error.message || 'Erreur de chargement', 'error');
    }
  }

  destroy() {
    this._stopPolling();
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
    if (this._onKeydown) {
      document.removeEventListener('keydown', this._onKeydown);
      this._onKeydown = null;
    }
    if (this.element) this.element.remove();
    this.element = null;
  }

  // ------------------------------------------------------------- chargement

  async _loadAlbums() {
    const result = await listAlbums({ page_size: 200 });
    this.albums = result.items || [];
  }

  async _loadPeople() {
    const result = await listPeople();
    this.people = result.items || [];
  }

  async _loadPlaces() {
    const result = await listPlaces();
    this.places = result.items || [];
  }

  async _loadPersonFaces() {
    if (!this.filter || this.filter.type !== 'person') {
      this.personFaces = [];
      return;
    }
    try {
      const result = await listPersonFaces(this.filter.id);
      this.personFaces = result.items || [];
    } catch {
      this.personFaces = [];
    }
  }

  _hideFacesPanel() {
    const panel = this.element && this.element.querySelector('[data-faces-panel]');
    if (!panel) return;
    panel.hidden = true;
    panel.innerHTML = '';
  }

  _renderFacesPanel() {
    const panel = this.element && this.element.querySelector('[data-faces-panel]');
    if (!panel) return;
    if (!this.filter || this.filter.type !== 'person') {
      this._hideFacesPanel();
      return;
    }
    const faces = this.personFaces || [];
    const canManage = this._can('photos.people.manage');
    const others = this.people.filter((p) => p.id !== this.filter.id);
    panel.hidden = false;
    panel.innerHTML = `
      <div class="photos-faces-header">
        <h3>Visages — ${this._esc(this.filter.name)} (${faces.length})</h3>
        ${canManage && others.length ? `
          <div class="photos-faces-merge">
            <select class="form-control" data-merge-target>
              <option value="">Fusionner avec…</option>
              ${others.map((p) => `<option value="${p.id}">${this._esc(p.name)}</option>`).join('')}
            </select>
            <button type="button" class="btn btn-secondary btn-sm" data-merge-go>Fusionner ici</button>
          </div>` : ''}
      </div>
      ${faces.length ? `
        <div class="photos-faces-grid">
          ${faces.map((face) => `
            <div class="photos-face" data-face="${face.id}">
              <img src="${faceCropUrl(face.id, 'small')}" alt="Visage" loading="lazy">
              <div class="photos-face-actions">
                ${canManage ? `
                  <button type="button" class="btn btn-secondary btn-sm"
                          data-face-cover="${face.id}" title="Couverture du groupe">★</button>
                  <button type="button" class="btn btn-danger btn-sm"
                          data-face-unassign="${face.id}" title="Retirer du groupe">✕</button>` : ''}
              </div>
            </div>`).join('')}
        </div>` : '<p class="empty-message">Aucun visage détecté pour cette personne.</p>'}
    `;
    this._bindFacesPanelActions(panel);
  }

  _bindFacesPanelActions(panel) {
    const mergeGo = panel.querySelector('[data-merge-go]');
    if (mergeGo) {
      mergeGo.addEventListener('click', async () => {
        const select = panel.querySelector('[data-merge-target]');
        const sourceId = Number(select && select.value);
        if (!sourceId) return;
        const source = this.people.find((p) => p.id === sourceId);
        if (!confirm(`Fusionner « ${source ? source.name : sourceId} » dans « ${this.filter.name} » ?`)) return;
        try {
          await mergePeople(this.filter.id, sourceId);
          await this._loadPeople();
          await this._loadPersonFaces();
          const merged = this.people.find((p) => p.id === this.filter.id);
          if (merged) this.filter.name = merged.name;
          this._renderFacesPanel();
          this._renderCards();
          this._toast('Personnes fusionnées');
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
        }
      });
    }
    panel.querySelectorAll('[data-face-cover]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await setPersonCover(this.filter.id, Number(btn.dataset.faceCover));
          await this._loadPeople();
          this._toast('Couverture définie');
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
        }
      });
    });
    panel.querySelectorAll('[data-face-unassign]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!confirm('Retirer ce visage du groupe ?')) return;
        try {
          await unassignFace(Number(btn.dataset.faceUnassign));
          await this._loadPersonFaces();
          this._renderFacesPanel();
          this._toast('Visage retiré du groupe');
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
        }
      });
    });
  }

  _listParams(cursor = null) {
    const params = { page_size: PAGE_SIZE };
    if (cursor) params.cursor = cursor;
    if (this.view === 'favorites') params.favorite = true;
    if (this.filter) {
      if (this.filter.type === 'album') params.album_id = this.filter.id;
      if (this.filter.type === 'person') params.person_id = this.filter.id;
      if (this.filter.type === 'place') params.place_id = this.filter.id;
    }
    return params;
  }

  async _resetGrid() {
    this.photos = [];
    this.cursor = null;
    this.hasMore = true;
    this._renderGrid();
    await this._loadMore();
  }

  async _loadMore() {
    if (this.loading || !this.hasMore) return;
    this.loading = true;
    try {
      let result;
      if (this.searchQuery) {
        result = await searchPhotos(this.searchQuery, this._listParams(this.cursor));
      } else {
        result = await listPhotos(this._listParams(this.cursor));
      }
      const items = result.items || [];
      this.photos = this.photos.concat(items);
      this.cursor = result.next_cursor || null;
      this.hasMore = Boolean(this.cursor);
      this._renderGrid();
      this._schedulePolling();
    } catch (error) {
      this._toast(error.message || 'Erreur de chargement', 'error');
    } finally {
      this.loading = false;
    }
  }

  // ------------------------------------------------------------- polling

  _schedulePolling() {
    this._stopPolling();
    const hasPending = this.photos.some(
      (p) => p.status === 'pending'
        || p.status === 'processing'
        || p.analysis_status === 'pending'
        || p.analysis_status === 'running',
    );
    if (!hasPending) return;
    this.pollHandle = setTimeout(async () => {
      try {
        const scrollY = window.scrollY;
        await this._resetGrid();
        window.scrollTo(0, scrollY);
      } catch { /* le prochain cycle réessaiera */ }
    }, 3000);
  }

  _stopPolling() {
    if (this.pollHandle) {
      clearTimeout(this.pollHandle);
      this.pollHandle = null;
    }
  }

  // ------------------------------------------------------------- rendu

  _viewTitle() {
    if (this.filter) return this.filter.name;
    return {
      all: 'Photos',
      favorites: 'Favoris',
      albums: 'Albums',
      people: 'Personnes',
      places: 'Lieux',
    }[this.view] || 'Photos';
  }

  _viewSubtitle() {
    return {
      all: 'Votre galerie personnelle',
      favorites: 'Vos photos favorites',
      albums: 'Regrouper vos photos en albums',
      people: 'Personnes reconnues dans vos photos',
      places: 'Lieux extraits des données GPS',
    }[this.view] || '';
  }

  _isGridView() {
    return this.view === 'all' || this.view === 'favorites' || Boolean(this.filter);
  }

  _can(perm) {
    try { return authStore.hasPermission(perm); } catch { return false; }
  }

  _renderHeaderActions() {
    const container = this.element.querySelector('[data-header-actions]');
    if (!container) return;
    const showUpload = (this.view === 'all' || this.view === 'favorites' || this.filter)
      && this._can('photos.upload');
    const showCreate = ['albums', 'people'].includes(this.view);
    const showStorage = this._can('photos.view');
    container.innerHTML = `
      ${showUpload ? '<button type="button" class="btn btn-primary" data-action="upload">Importer</button>' : ''}
      ${showCreate ? '<button type="button" class="btn btn-primary" data-action="create">Créer</button>' : ''}
      ${showStorage ? '<button type="button" class="btn btn-secondary" data-action="storage">Stockage</button>' : ''}
      <input type="file" accept="image/*" multiple data-upload-input hidden>
    `;
    if (showUpload) {
      const input = container.querySelector('[data-upload-input]');
      container.querySelector('[data-action="upload"]').addEventListener('click', () => input.click());
      input.addEventListener('change', async () => {
        if (!input.files || !input.files.length) return;
        try {
          const result = await uploadPhotos(input.files);
          const errors = result.errors || [];
          if (errors.length) {
            this._toast(`${result.items.length} importée(s), ${errors.length} échec(s)`, 'error');
          } else {
            this._toast(`${result.items.length} photo(s) importée(s)`);
          }
          input.value = '';
          await this._resetGrid();
        } catch (error) {
          this._toast(error.message || 'Import impossible', 'error');
        }
      });
    }
    if (showCreate) {
      container.querySelector('[data-action="create"]').addEventListener('click', () => {
        if (this.view === 'albums') this._createAlbum();
        else this._createPerson();
      });
    }
    if (showStorage) {
      container
        .querySelector('[data-action="storage"]')
        .addEventListener('click', () => this._toggleStoragePanel());
    }
  }

  // ------------------------------------------------------------- stockage (V3)

  async _toggleStoragePanel() {
    const panel = this.element?.querySelector('[data-storage-panel]');
    if (!panel) return;
    if (!panel.hidden) {
      panel.hidden = true;
      panel.innerHTML = '';
      return;
    }
    panel.hidden = false;
    panel.innerHTML = '<p class="photos-storage-loading">Chargement…</p>';
    await this._refreshStoragePanel();
  }

  async _refreshStoragePanel() {
    const panel = this.element?.querySelector('[data-storage-panel]');
    if (!panel || panel.hidden) return;
    try {
      const status = await getStorageStatus();
      this._renderStoragePanel(panel, status);
    } catch (error) {
      panel.innerHTML = `<p class="photos-storage-error">${this._esc(
        error.message || 'Statut du stockage indisponible'
      )}</p>`;
    }
  }

  _renderStoragePanel(panel, status) {
    const run = status.last_scan;
    const stateLabels = { available: 'disponible', unavailable: 'indisponible', error: 'erreur' };
    const stateClass =
      status.state === 'available' ? 'is-ok' : status.state === 'error' ? 'is-error' : 'is-warn';
    const runWhen = run ? run.finished_at || run.started_at || '' : '';
    const scanLine = run
      ? `Dernier scan : ${this._esc(runWhen.replace('T', ' ').slice(0, 16))} — ` +
        `${run.files_seen} fichier(s), ${run.created} créé(s), ` +
        `${run.updated_paths} déplacé(s), ${run.missing_marked} manquant(s) — ` +
        `état ${this._esc(run.state)}`
      : 'Dernier scan : aucun';
    panel.innerHTML = `
      <div class="photos-storage-head">
        <strong>Stockage</strong>
        <button type="button" class="photos-storage-close" data-storage-close aria-label="Fermer">✕</button>
      </div>
      <div class="photos-storage-rows">
        <div class="photos-storage-row"><span>Backend</span><code>${this._esc(status.backend)}</code></div>
        <div class="photos-storage-row"><span>Chemin</span><code>${this._esc(status.path)}</code></div>
        <div class="photos-storage-row"><span>Statut</span>
          <span class="photos-storage-badge ${stateClass}">${this._esc(
            stateLabels[status.state] || status.state
          )}</span>
          <span class="photos-storage-detail">${this._esc(status.detail)}</span></div>
        <div class="photos-storage-row"><span>Scan auto</span><span>${
          status.scan_enabled
            ? `activé (toutes les ${status.scan_interval_seconds} s)`
            : 'désactivé'
        }</span></div>
        <div class="photos-storage-row photos-storage-row--scan"><span>${scanLine}</span></div>
      </div>
      <div class="photos-storage-actions">
        ${this._can('photos.upload') ? '<button type="button" class="btn btn-primary btn-sm" data-storage-scan>Scanner maintenant</button>' : ''}
        ${this._can('photos.analyze') ? '<button type="button" class="btn btn-secondary btn-sm" data-storage-rebuild>Miniatures manquantes</button>' : ''}
        <button type="button" class="btn btn-secondary btn-sm" data-storage-refresh>Vérifier le stockage</button>
      </div>
    `;
    panel.querySelector('[data-storage-close]').addEventListener('click', () => {
      panel.hidden = true;
      panel.innerHTML = '';
    });
    const refreshBtn = panel.querySelector('[data-storage-refresh]');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => this._refreshStoragePanel());
    }
    const scanBtn = panel.querySelector('[data-storage-scan]');
    if (scanBtn) {
      scanBtn.addEventListener('click', async () => {
        scanBtn.disabled = true;
        try {
          const result = await startStorageScan();
          this._toast(result.message || 'Scan mis en file');
          setTimeout(async () => {
            try {
              await this._refreshStoragePanel();
              await this._resetGrid();
            } catch { /* le rafraîchissement n'interrompt pas le scan */ }
          }, 1500);
        } catch (error) {
          this._toast(error.message || 'Scan impossible', 'error');
          scanBtn.disabled = false;
        }
      });
    }
    const rebuildBtn = panel.querySelector('[data-storage-rebuild]');
    if (rebuildBtn) {
      rebuildBtn.addEventListener('click', async () => {
        rebuildBtn.disabled = true;
        try {
          const result = await rebuildThumbnails();
          this._toast(result.message || 'Regénération des miniatures lancée');
          setTimeout(async () => {
            try {
              await this._refreshStoragePanel();
              await this._resetGrid();
            } catch { /* le rafraîchissement n'interrompt pas le rebuild */ }
          }, 1500);
        } catch (error) {
          this._toast(error.message || 'Regénération impossible', 'error');
          rebuildBtn.disabled = false;
        }
      });
    }
  }

  _bindToolbar() {
    const search = this.element.querySelector('[data-search]');
    if (search) {
      let handle = null;
      search.addEventListener('input', () => {
        clearTimeout(handle);
        handle = setTimeout(async () => {
          this.searchQuery = search.value.trim();
          if (this.view === 'albums' || this.view === 'people' || this.view === 'places') {
            this.router.navigate('/photos');
            return;
          }
          await this._resetGrid();
        }, 400);
      });
    }
    const clear = this.element.querySelector('[data-action="clear-filter"]');
    if (clear) {
      clear.addEventListener('click', () => {
        this.filter = null;
        this._rerender();
      });
    }
    this.element.querySelectorAll('[data-smart-q]').forEach((chip) => {
      chip.addEventListener('click', async () => {
        this.searchQuery = chip.dataset.smartQ || '';
        const input = this.element.querySelector('[data-search]');
        if (input) input.value = this.searchQuery;
        if (!this._isGridView()) {
          this.router.navigate('/photos');
          return;
        }
        await this._resetGrid();
      });
    });
    this._observeSentinel();
  }

  _observeSentinel() {
    const sentinel = this.element.querySelector('[data-sentinel]');
    if (!sentinel) return;
    if (this.observer) this.observer.disconnect();
    this.observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) this._loadMore();
    }, { rootMargin: '600px' });
    this.observer.observe(sentinel);
  }

  _renderCards() {
    const container = this.element.querySelector('[data-cards]');
    const grid = this.element.querySelector('[data-grid]');
    if (!container || !grid) return;

    if (this.view === 'albums') {
      container.innerHTML = this.albums.length ? `
        <div class="photos-card-grid">
          ${this.albums.map((album) => `
            <div class="photos-card" data-album="${album.id}">
              <div class="photos-card-cover">
                ${album.cover_photo_id
                  ? `<img src="${photoFileUrl(album.cover_photo_id, 'small')}" alt="" loading="lazy">`
                  : '<span class="photos-card-placeholder">📁</span>'}
              </div>
              <div class="photos-card-body">
                <strong>${this._esc(album.name)}</strong>
                <span>${album.photo_count} photo(s)</span>
              </div>
              <div class="photos-card-actions">
                ${this._can('photos.albums.manage') ? `
                  <button type="button" class="btn btn-secondary btn-sm" data-rename="${album.id}">Renommer</button>
                  <button type="button" class="btn btn-danger btn-sm" data-delete="${album.id}">Suppr.</button>` : ''}
              </div>
            </div>`).join('')}
        </div>` : '<p class="empty-message">Aucun album. Créez le premier.</p>';
      container.hidden = Boolean(this.filter);
      grid.hidden = !this.filter;
      container.querySelectorAll('[data-album]').forEach((card) => {
        card.querySelector('strong').addEventListener('click', () => {
          const album = this.albums.find((a) => a.id === Number(card.dataset.album));
          this.filter = { type: 'album', id: album.id, name: album.name };
          this._rerender();
        });
      });
      container.querySelectorAll('[data-rename]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const album = this.albums.find((a) => a.id === Number(btn.dataset.rename));
          this._renameAlbum(album);
        });
      });
      container.querySelectorAll('[data-delete]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const album = this.albums.find((a) => a.id === Number(btn.dataset.delete));
          if (!confirm(`Supprimer l'album « ${album.name} » ?`)) return;
          try {
            await deleteAlbum(album.id);
            this._toast('Album supprimé');
            await this._loadAlbums();
            this._renderCards();
          } catch (error) {
            this._toast(error.message || 'Erreur', 'error');
          }
        });
      });
    } else if (this.view === 'people') {
      container.innerHTML = this.people.length ? `
        <div class="photos-card-grid">
          ${this.people.map((person) => `
            <div class="photos-card" data-person="${person.id}">
              <div class="photos-card-cover">
                ${person.cover_face_id
                  ? `<img src="${faceCropUrl(person.cover_face_id, 'small')}" alt="" loading="lazy">`
                  : '<span class="photos-card-placeholder">👤</span>'}
              </div>
              <div class="photos-card-body">
                <strong>${this._esc(person.name)}</strong>
                <span>${person.photo_count} photo(s) · ${person.face_count || 0} visage(s)</span>
              </div>
              <div class="photos-card-actions">
                ${this._can('photos.people.manage') ? `
                  <button type="button" class="btn btn-secondary btn-sm" data-rename="${person.id}">Renommer</button>
                  <button type="button" class="btn btn-danger btn-sm" data-delete="${person.id}">Suppr.</button>` : ''}
              </div>
            </div>`).join('')}
        </div>` : '<p class="empty-message">Aucune personne identifiée.</p>';
      container.hidden = Boolean(this.filter);
      grid.hidden = !this.filter;
      container.querySelectorAll('[data-person]').forEach((card) => {
        card.querySelector('strong').addEventListener('click', () => {
          const person = this.people.find((p) => p.id === Number(card.dataset.person));
          this.filter = { type: 'person', id: person.id, name: person.name };
          this._rerender();
        });
      });
      container.querySelectorAll('[data-rename]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const person = this.people.find((p) => p.id === Number(btn.dataset.rename));
          const name = prompt('Nouveau nom', person.name);
          if (!name || name === person.name) return;
          try {
            await updatePerson(person.id, name);
            this._toast('Personne renommée');
            await this._loadPeople();
            this._renderCards();
          } catch (error) {
            this._toast(error.message || 'Erreur', 'error');
          }
        });
      });
      container.querySelectorAll('[data-delete]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const person = this.people.find((p) => p.id === Number(btn.dataset.delete));
          if (!confirm(`Supprimer « ${person.name} » ? Les photos ne sont pas supprimées.`)) return;
          try {
            await deletePerson(person.id);
            this._toast('Personne supprimée');
            await this._loadPeople();
            this._renderCards();
          } catch (error) {
            this._toast(error.message || 'Erreur', 'error');
          }
        });
      });
    } else if (this.view === 'places') {
      container.innerHTML = this.places.length ? `
        <div class="photos-card-grid">
          ${this.places.map((place) => `
            <div class="photos-card" data-place="${place.id}">
              <div class="photos-card-cover">
                <span class="photos-card-placeholder">📍</span>
              </div>
              <div class="photos-card-body">
                <strong>${this._esc(place.label || `${place.lat_cell}, ${place.lon_cell}`)}</strong>
                <span>${place.photo_count} photo(s)</span>
              </div>
            </div>`).join('')}
        </div>` : '<p class="empty-message">Aucun lieu (photos sans GPS).</p>';
      container.hidden = Boolean(this.filter);
      grid.hidden = !this.filter;
      container.querySelectorAll('[data-place]').forEach((card) => {
        card.querySelector('strong').addEventListener('click', () => {
          const place = this.places.find((p) => p.id === Number(card.dataset.place));
          const name = place.label || `${place.lat_cell}, ${place.lon_cell}`;
          this.filter = { type: 'place', id: place.id, name };
          this._rerender();
        });
      });
    } else {
      container.innerHTML = '';
      container.hidden = true;
      grid.hidden = false;
    }
  }

  _renderGrid() {
    const grid = this.element.querySelector('[data-grid]');
    const empty = this.element.querySelector('[data-empty]');
    const count = this.element.querySelector('[data-count]');
    if (!grid) return;
    if (count) count.textContent = this.photos.length ? `${this.photos.length} photo(s)` : '';
    if (empty) empty.hidden = this.photos.length > 0 || this.loading;

    grid.innerHTML = this.photos.map((photo) => {
      const title = photo.title || photo.original_filename;
      const pending = photo.status !== 'ready';
      const analyzing = photo.analysis_status === 'pending' || photo.analysis_status === 'running';
      const analysisFailed = photo.analysis_status === 'failed';
      const isVideo = photo.mime_type?.startsWith('video/');
      return `
        <div class="photos-tile ${pending ? 'is-pending' : ''}${isVideo ? ' is-video' : ''}" data-photo="${photo.id}" title="${this._esc(title)}">
          <img src="${photoFileUrl(photo.id, 'tiny')}" alt="${this._esc(title)}" loading="lazy">
          ${pending ? '<span class="photos-tile-status">…</span>' : ''}
          ${photo.status === 'failed' ? '<span class="photos-tile-status is-error">!</span>' : ''}
          ${analyzing ? '<span class="photos-tile-ai" title="Analyse IA en cours"></span>' : ''}
          ${analysisFailed ? '<span class="photos-tile-ai is-error" title="Analyse IA en échec"></span>' : ''}
          ${isVideo ? '<span class="photos-tile-video" title="Vidéo">▶</span>' : ''}
          <button type="button" class="photos-tile-fav ${photo.is_favorite ? 'is-on' : ''}"
                  data-fav="${photo.id}" title="Favori">★</button>
          <span class="photos-tile-title">${this._esc(title)}</span>
        </div>`;
    }).join('');

    grid.querySelectorAll('[data-photo]').forEach((tile) => {
      tile.addEventListener('click', (event) => {
        if (event.target.closest('[data-fav]')) return;
        this._openLightbox(Number(tile.dataset.photo));
      });
      // Miniature échouée : marquer la tuile pour affichage dégradé (CSS)
      const img = tile.querySelector('img');
      if (img) {
        img.addEventListener('error', () => tile.classList.add('is-nothumb'), { once: true });
      }
    });
    });
    grid.querySelectorAll('[data-fav]').forEach((btn) => {
      btn.addEventListener('click', async (event) => {
        event.stopPropagation();
        if (!this._can('photos.update')) return;
        const id = Number(btn.dataset.fav);
        const photo = this.photos.find((p) => p.id === id);
        try {
          await updatePhoto(id, { is_favorite: !photo.is_favorite });
          photo.is_favorite = !photo.is_favorite;
          btn.classList.toggle('is-on', photo.is_favorite);
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
        }
      });
    });
    this._observeSentinel();
  }

  async _rerender() {
    if (!this.element) return;
    const parent = this.element.parentNode;
    const old = this.element;
    const fresh = this.render();
    parent.replaceChild(fresh, old);
    await this.loadData();
  }

  // ------------------------------------------------------------- lightbox

  _bindLightbox() {
    this.element.querySelectorAll('[data-action="close-lightbox"]').forEach((btn) => {
      btn.addEventListener('click', () => this._closeLightbox());
    });
    if (this._onKeydown) document.removeEventListener('keydown', this._onKeydown);
    this._onKeydown = (event) => {
      if (event.key === 'Escape') this._closeLightbox();
    };
    document.addEventListener('keydown', this._onKeydown);
  }

  async _openLightbox(photoId) {
    const lightbox = this.element.querySelector('[data-lightbox]');
    if (!lightbox) return;
    try {
      this.detail = await getPhoto(photoId);
    } catch (error) {
      this._toast(error.message || 'Photo introuvable', 'error');
      return;
    }
    lightbox.hidden = false;
    this._renderLightbox();
  }

  _closeLightbox() {
    const lightbox = this.element && this.element.querySelector('[data-lightbox]');
    if (lightbox) lightbox.hidden = true;
    this.detail = null;
  }

  _renderLightbox() {
    const detail = this.detail;
    if (!detail) return;
    const media = this.element.querySelector('[data-lightbox-media]');
    const info = this.element.querySelector('[data-lightbox-info]');
    if (!media || !info) return;

    const isVideo = detail.mime_type?.startsWith('video/');
    const activeEdit = (detail.edits || []).find((edit) => edit.is_active);
    // L'original pour la vidéo (pas de retouche), sinon la miniature 'large'
    const src = activeEdit
      ? `${editFileUrl(detail.id, activeEdit.id)}?v=${this.lightboxImageNonce}`
      : `${photoFileUrl(detail.id, isVideo ? 'original' : 'large')}&v=${this.lightboxImageNonce}`;

    if (isVideo) {
      media.innerHTML = `<video controls preload="metadata" src="${src}" title="${this._esc(detail.title || detail.original_filename)}"></video>`;
    } else {
      media.innerHTML = `<img src="${src}" alt="${this._esc(detail.title || detail.original_filename)}">`;
    }

    const tags = detail.tags || [];
    info.innerHTML = `
      <h2>${this._esc(detail.title || detail.original_filename)}</h2>
      <p class="photos-meta">
        ${detail.width && detail.height ? `${detail.width}×${detail.height} · ` : ''}
        ${this._formatBytes(detail.byte_size)}<br>
        Prise le ${this._formatDate(detail.taken_at)}<br>
        Importée le ${this._formatDate(detail.imported_at)}
        ${detail.camera_model ? `<br>${this._esc(detail.camera_make || '')} ${this._esc(detail.camera_model)}` : ''}
        ${detail.gps_latitude != null ? `<br>GPS : ${detail.gps_latitude.toFixed(3)}, ${detail.gps_longitude.toFixed(3)}` : ''}
        ${detail.place ? `<br>Lieu : ${this._esc(detail.place.label || '')}` : ''}
        <br>Visages : ${detail.face_count ?? 0}
        <br>Analyse IA : ${this._analysisLabel(detail.analysis_status)}
      </p>

      <div class="photos-lightbox-actions">
        <button type="button" class="btn btn-secondary btn-sm" data-action="lb-fav">
          ${detail.is_favorite ? '★ Retirer des favoris' : '☆ Ajouter aux favoris'}
        </button>
        ${this._can('photos.delete') ? '<button type="button" class="btn btn-danger btn-sm" data-action="lb-delete">Supprimer</button>' : ''}
        ${detail.is_deleted ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-restore">Restaurer</button>' : ''}
        ${this._can('photos.analyze') ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-analyze">Analyser</button>' : ''}
        ${this._can('photos.analyze') ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-reindex">Ré-indexer</button>' : ''}
        ${this._can('photos.analyze') ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-faces">Détecter visages</button>' : ''}
      </div>

      ${this._can('photos.edit') ? `
        <div class="photos-lightbox-actions">
          <button type="button" class="btn btn-secondary btn-sm" data-action="lb-rotate">Rotation 90°</button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="lb-enhance">Amélioration auto</button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="lb-revert">Rétablir l'original</button>
        </div>` : ''}

      <h3>Tags</h3>
      <div class="photos-tags">
        ${tags.map((tag) => `
          <span class="photos-tag">${this._esc(tag.name)}
            ${this._can('photos.update') ? `<button type="button" data-rmtag="${tag.id}" aria-label="Retirer">✕</button>` : ''}
          </span>`).join('') || '<span class="empty-message">Aucun tag</span>'}
      </div>
      ${this._can('photos.update') ? `
        <form class="photos-tag-form" data-tag-form>
          <input class="form-control" name="tag" maxlength="120" placeholder="Ajouter un tag" required>
          <button class="btn btn-secondary btn-sm" type="submit">Ajouter</button>
        </form>` : ''}
    `;

    this._bindLightboxActions();
  }

  _bindLightboxActions() {
    const info = this.element.querySelector('[data-lightbox-info]');
    const detail = this.detail;
    if (!info || !detail) return;
    const on = (action, handler) => {
      const el = info.querySelector(`[data-action="${action}"]`);
      if (el) el.addEventListener('click', handler);
    };

    on('lb-fav', async () => {
      if (!this._can('photos.update')) return;
      try {
        await updatePhoto(detail.id, { is_favorite: !detail.is_favorite });
        this.detail = await getPhoto(detail.id);
        this._renderLightbox();
        await this._refreshGridSilently();
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });

    on('lb-delete', async () => {
      if (!confirm('Supprimer cette photo ?')) return;
      try {
        await deletePhoto(detail.id);
        this._closeLightbox();
        this._toast('Photo supprimée');
        await this._refreshGridSilently();
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });

    on('lb-restore', async () => {
      try {
        this.detail = await restorePhoto(detail.id);
        this._renderLightbox();
        await this._refreshGridSilently();
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });

    on('lb-analyze', async () => {
      try {
        await analyzePhoto(detail.id);
        this._toast('Analyse lancée');
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });

    on('lb-reindex', async () => {
      try {
        await reindexPhoto(detail.id);
        this._toast('Ré-indexation lancée');
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });

    on('lb-faces', async () => {
      try {
        await reindexFaces(detail.id);
        this._toast('Détection des visages lancée');
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });

    on('lb-rotate', () => this._applyEdit({ kind: 'rotate', params: { degrees: 90 }, name: 'Rotation 90°' }));
    on('lb-enhance', () => this._applyEdit({ kind: 'auto_enhance', name: 'Amélioration auto' }));
    on('lb-revert', async () => {
      try {
        await revertPhoto(detail.id);
        this.lightboxImageNonce += 1;
        this.detail = await getPhoto(detail.id);
        this._renderLightbox();
        this._toast("Retour à l'original");
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });

    info.querySelectorAll('[data-rmtag]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          await removePhotoTag(detail.id, Number(btn.dataset.rmtag));
          this.detail = await getPhoto(detail.id);
          this._renderLightbox();
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
        }
      });
    });

    const tagForm = info.querySelector('[data-tag-form]');
    if (tagForm) {
      tagForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const name = new FormData(tagForm).get('tag');
        if (!name) return;
        try {
          await addPhotoTag(detail.id, String(name).trim());
          this.detail = await getPhoto(detail.id);
          this._renderLightbox();
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
        }
      });
    }
  }

  async _applyEdit(payload) {
    const detail = this.detail;
    try {
      await createEdit(detail.id, payload);
      this.lightboxImageNonce += 1;
      this.detail = await getPhoto(detail.id);
      this._renderLightbox();
      this._toast('Retouche appliquée');
      await this._refreshGridSilently();
    } catch (error) {
      this._toast(error.message || 'Retouche impossible', 'error');
    }
  }

  async _refreshGridSilently() {
    if (this.view === 'albums' || this.view === 'people' || this.view === 'places') {
      if (!this.filter) return;
    }
    try {
      const result = this.searchQuery
        ? await searchPhotos(this.searchQuery, this._listParams())
        : await listPhotos(this._listParams());
      this.photos = result.items || [];
      this.cursor = result.next_cursor || null;
      this.hasMore = Boolean(this.cursor);
      this._renderGrid();
    } catch { /* la grille reste telle quelle */ }
  }

  // ------------------------------------------------------------- albums / personnes

  async _createAlbum() {
    const name = prompt("Nom de l'album ?");
    if (!name) return;
    try {
      await createAlbum({ name: name.trim() });
      this._toast('Album créé');
      await this._loadAlbums();
      this._renderCards();
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
    }
  }

  async _renameAlbum(album) {
    const name = prompt('Nouveau nom', album.name);
    if (!name || name === album.name) return;
    try {
      await updateAlbum(album.id, { name: name.trim() });
      this._toast('Album renommé');
      await this._loadAlbums();
      this._renderCards();
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
    }
  }

  async _createPerson() {
    const name = prompt('Nom de la personne ?');
    if (!name) return;
    try {
      await createPerson(name.trim());
      this._toast('Personne créée');
      await this._loadPeople();
      this._renderCards();
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
    }
  }

  // ------------------------------------------------------------- utilitaires

  _analysisLabel(status) {
    return {
      pending: 'en attente',
      running: 'en cours…',
      done: 'terminée',
      failed: 'échec',
      skipped: 'ignorée',
    }[status] || status || '-';
  }

  _toast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  _esc(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  _formatBytes(bytes) {
    if (!bytes) return '0 o';
    const units = ['o', 'Ko', 'Mo', 'Go'];
    let i = 0;
    let value = bytes;
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024;
      i += 1;
    }
    return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  _formatDate(value) {
    if (!value) return '-';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString('fr-FR');
  }
}

export function createPhotosPage(router) {
  return new PhotosPage(router);
}
