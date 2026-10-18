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
  emptyTrash,
  faceCropUrl,
  geocodePlaces,
  getPhoto,
  getStorageStatus,
  getTimeline,
  hardDeletePhoto,
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
  restorePhoto,
  searchPhotos,
  setPersonCover,
  startStorageScan,
  unassignFace,
  updateAlbum,
  updatePerson,
  updatePhoto,
  uploadPhotos,
} from '../services/photosApi.js?v=8';
import { authStore } from '../stores/auth.js';

const PAGE_SIZE = 60;

function dbg(...args) {
  console.debug('[PHOTOS]', ...args);
}

// Décrit l'élément qui porte réellement le scroll vertical.
function describeScroller() {
  const candidates = [document.scrollingElement, ...document.querySelectorAll('*')];
  for (const el of candidates) {
    const style = getComputedStyle(el);
    if ((style.overflowY === 'auto' || style.overflowY === 'scroll')
      && el.scrollHeight > el.clientHeight + 50) {
      return `${el.tagName.toLowerCase()}.${String(el.className || '').split(' ')[0]}`;
    }
  }
  return 'window';
}

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
    this.dateFrom = null;
    this.dateTo = null;
    this.albums = [];
    this.people = [];
    this.personFaces = [];
    this.places = [];
    this.detail = null;
    this.pollHandle = null;
    this.observer = null;
    this.lightboxImageNonce = 0;
    this.selectedPhotos = new Set();  // IDs des photos sélectionnées
    this.multiSelectMode = false;
    // Mode chronologique : 'days' (défaut) | 'months' | 'years'.
    this.timeline = 'days';
    this.periodGroups = [];
    this.periodTotal = 0;
    this._lastDayKey = null;
    // Génération de chargement : invalide les réponses en vol lors d'un
    // changement de vue/filtre (évite d'afficher l'ancienne liste).
    this._loadSeq = 0;
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
    this._loadSeq += 1;
  }

  render() {
    this._bulkBound = false;
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
        <div class="photos-date-filter" data-date-filter>
          <select class="form-control form-control-sm" data-year title="Année">
            <option value="">Toutes les années</option>
          </select>
          <select class="form-control form-control-sm" data-month title="Mois" disabled>
            <option value="">Tous les mois</option>
          </select>
          <button type="button" class="btn btn-secondary btn-sm" data-action="clear-date" hidden>✕</button>
        </div>
        ${this._isGridView() && !this.filter ? `
        <div class="photos-timeline" data-timeline role="group" aria-label="Affichage chronologique">
          <button type="button" data-tl="years">Années</button>
          <button type="button" data-tl="months">Mois</button>
          <button type="button" data-tl="days">Jours</button>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" data-action="tl-back" hidden></button>` : ''}
        <span class="photos-count" data-count></span>
      </div>

      <div class="photos-bulk-toolbar" data-bulk-toolbar hidden>
        <span class="bulk-count" data-bulk-count></span>
        <div class="bulk-actions">
          <button type="button" class="btn btn-danger btn-sm" data-action="bulk-delete" title="Supprimer">🗑</button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="bulk-cancel">Annuler</button>
          <button type="button" class="btn btn-secondary btn-sm" data-action="bulk-fav" title="Favori">★</button>
        </div>
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
    this._syncTimelineUi();
    this._syncDateSelects();
    this._bindLightbox();
    return this.element;
  }

  async loadData() {
    this._stopPolling();
    this._onScroll = this._onScroll.bind(this);
    // Le scroll vertical est porté par .main-content (layout à hauteur fixe),
    // window ne scrolle plus : on s'abonne au conteneur réel.
    this._scroller = document.querySelector('.main-content') || window;
    this._scroller.addEventListener('scroll', this._onScroll, { passive: true });
    dbg('loadData view=', this.view, 'scrollContainer=', describeScroller());
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
      } else if (this.view === 'trash') {
        await this._loadTrash();
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

  _onScroll() {
    const el = this._scroller;
    const isWindow = !el || el === window;
    const docHeight = isWindow ? document.documentElement.scrollHeight : el.scrollHeight;
    const scrollPos = isWindow
      ? window.scrollY + window.innerHeight
      : el.scrollTop + el.clientHeight;
    const threshold = docHeight - 300;
    const nearBottom = scrollPos >= threshold;
    dbg('scroll photos=', this.photos.length, 'loading=', this.loading,
      'hasMore=', this.hasMore, 'docHeight=', docHeight, 'scrollPos=', scrollPos,
      'threshold=', threshold, 'nearBottom=', nearBottom);
    if (this.loading) return;
    if (nearBottom) {
      dbg('scroll → loadMore');
      this._loadMore();
    }
  }

  destroy() {
    this._stopPolling();
    this._stopPlacesGeocodePolling();
    if (this.placesMap) { this.placesMap.remove(); this.placesMap = null; }
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
    if (this._onKeydown) {
      document.removeEventListener('keydown', this._onKeydown);
      this._onKeydown = null;
    }
    if (this._onScroll) {
      const el = this._scroller || window;
      el.removeEventListener('scroll', this._onScroll);
      this._onScroll = null;
      this._scroller = null;
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

  async _loadTrash() {
    this.photos = [];
    this.cursor = null;
    this.hasMore = true;
    this._loadSeq += 1;
    await this._loadMore();
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
    if (this.view === 'trash') params.trashed = true;
    if (this.dateFrom) params.date_from = this.dateFrom;
    if (this.dateTo) params.date_to = this.dateTo;
    if (this.filter) {
      if (this.filter.type === 'album') params.album_id = this.filter.id;
      if (this.filter.type === 'person') params.person_id = this.filter.id;
      if (this.filter.type === 'place') params.place_id = this.filter.id;
    }
    return params;
  }

  _updateBulkToolbar() {
    const toolbar = this.element.querySelector('[data-bulk-toolbar]');
    const countEl = this.element.querySelector('[data-bulk-count]');
    if (!toolbar || !countEl) return;
    const count = this.selectedPhotos.size;
    toolbar.hidden = count === 0;
    countEl.textContent = count > 0 ? `${count} photo(s) sélectionnée(s)` : '';
  }

  _isPhotoGalleryView() {
    // Vues qui affichent la grille de photos (les vues cartes albums/
    // personnes/lieux n'ont rien à faire dans _loadMore).
    return this.view === 'all' || this.view === 'favorites'
      || this.view === 'trash' || Boolean(this.filter);
  }

  _isPeriodView() {
    // Vues agrégées (Mois / Années) : réservées à la grille photos SANS filtre.
    // Avec un filtre (album, personne, lieu, recherche), on force l'affichage Jours.
    return this._isGridView() && !this.filter && this.timeline !== 'days';
  }

  async _resetGrid() {
    dbg('resetGrid (cursor reset) photos=', this.photos.length, 'cursor=', this.cursor);
    this.photos = [];
    this.cursor = null;
    this.hasMore = true;
    this._loadSeq += 1;
    this.selectedPhotos.clear();
    this._updateBulkToolbar();
    if (this._isPeriodView()) {
      await this._loadPeriods();
      return;
    }
    this._renderGrid();
    await this._loadMore();
  }

  // Agrégations Mois/Années : une requête /photos/timeline, aucune photo
  // chargée dans le navigateur.
  async _loadPeriods() {
    if (this.loading) return;
    this.loading = true;
    try {
      const params = this._listParams();
      delete params.page_size;
      delete params.cursor;
      params.interval = this.timeline === 'years' ? 'year' : 'month';
      if (this.searchQuery) params.q = this.searchQuery;
      const result = await getTimeline(params);
      this.periodGroups = result.groups || [];
      this.periodTotal = result.total || 0;
      dbg('loadPeriods', params.interval, 'groupes=', this.periodGroups.length,
        'total=', this.periodTotal);
      this._renderGrid();
      this._observeSentinel();
    } catch (error) {
      dbg('loadPeriods ERROR', error && error.message);
      this._toast(error.message || 'Erreur de chargement', 'error');
    } finally {
      this.loading = false;
    }
  }

  async _loadMore() {
    dbg('loadMore START photos=', this.photos.length, 'loading=', this.loading,
      'hasMore=', this.hasMore, 'nextCursor=', this.cursor);
    if (!this._isPhotoGalleryView() || this._isPeriodView()) return;
    if (this.loading || !this.hasMore) {
      dbg('loadMore skipped (loading=', this.loading, 'hasMore=', this.hasMore, ')');
      return;
    }
    this.loading = true;
    const seq = this._loadSeq;
    try {
      let result;
      if (this.searchQuery) {
        result = await searchPhotos(this.searchQuery, this._listParams(this.cursor));
      } else {
        result = await listPhotos(this._listParams(this.cursor));
      }
      if (seq !== this._loadSeq) {
        // Changement de vue/filtre pendant la requête : réponse obsolète.
        dbg('loadMore réponse obsolète (seq changé), ignorée');
        return;
      }
      const items = result.items || [];
      const prevCount = this.photos.length;
      this.photos = this.photos.concat(items);
      this.cursor = result.next_cursor || null;
      this.hasMore = Boolean(this.cursor);
      dbg('API returned', items.length, 'total photos=', this.photos.length,
        'newCursor=', this.cursor, 'hasMore AFTER=', this.hasMore);
      if (prevCount === 0) {
        this._renderGrid();
      } else {
        this._appendTiles(prevCount);
      }
      this._observeSentinel();
      this._schedulePolling();
    } catch (error) {
      dbg('loadMore ERROR', error && error.message);
      this._toast(error.message || 'Erreur de chargement', 'error');
    } finally {
      const stale = seq !== this._loadSeq;
      this.loading = false;
      if (stale) {
        // La vue a changé pendant la requête : la réponse a été ignorée et
        // le chargement de la nouvelle vue a été sauté (loading=true).
        dbg('loadMore stale → relance du chargement de la vue courante');
        this._loadMore();
      }
    }
  }

  // ------------------------------------------------------------- polling

  _schedulePolling() {
    this._stopPolling();
    // L'analyse IA « pending » peut rester en file d'attente des heures (jobs
    // d'arrière-plan) : elle ne doit pas maintenir un rafraîchissement
    // permanent de la grille. Seul un traitement réellement en cours
    // (import / génération de miniatures / analyse lancée) déclenche le poll.
    const hasPending = this.photos.some(
      (p) => p.status === 'pending'
        || p.status === 'processing'
        || p.analysis_status === 'running',
    );
    if (!hasPending) return;
    this.pollHandle = setTimeout(async () => {
      try {
        await this._refreshStatuses();
      } catch { /* le prochain cycle réessaiera */ }
    }, 3000);
  }

  // Rafraîchit les statuts des photos déjà chargées sans reconstituer la
  // grille : le scroll et les miniatures en cours de chargement sont conservés.
  async _refreshStatuses() {
    const pageSize = Math.min(Math.max(this.photos.length, PAGE_SIZE), 500);
    const params = { ...this._listParams(), page_size: pageSize };
    const result = this.searchQuery
      ? await searchPhotos(this.searchQuery, params)
      : await listPhotos(params);
    const fresh = result.items || [];
    const freshById = new Map(fresh.map((p) => [p.id, p]));
    const loadedIds = new Set(this.photos.map((p) => p.id));
    if (fresh.some((p) => !loadedIds.has(p.id))) {
      // Une photo est entrée en tête de liste : reconstruction complète.
      dbg('refreshStatuses → resetGrid (nouvelle photo en tête)');
      await this._resetGrid();
      return;
    }
    let changed = false;
    for (const photo of this.photos) {
      const next = freshById.get(photo.id);
      if (!next) continue;
      if (next.status !== photo.status
        || next.analysis_status !== photo.analysis_status
        || next.is_favorite !== photo.is_favorite) {
        photo.status = next.status;
        photo.analysis_status = next.analysis_status;
        photo.is_favorite = next.is_favorite;
        changed = true;
      }
    }
    if (changed) this._renderGrid();
    this._schedulePolling();
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
      trash: 'Corbeille',
    }[this.view] || 'Photos';
  }

  _viewSubtitle() {
    return {
      all: 'Votre galerie personnelle',
      favorites: 'Vos photos favorites',
      albums: 'Regrouper vos photos en albums',
      people: 'Personnes reconnues dans vos photos',
      places: 'Lieux extraits des données GPS',
      trash: 'Photos supprimées (restaurer ou supprimer définitivement)',
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
    const showSouvenirs = this._can('photos.view');
    const showGeocode = this.view === 'places' && this._can('photos.update');
    const showTrash = this.view === 'trash' && this._can('photos.delete');
    container.innerHTML = `
      ${showUpload ? '<button type="button" class="btn btn-primary" data-action="upload">Importer</button>' : ''}
      ${showCreate ? '<button type="button" class="btn btn-primary" data-action="create">Créer</button>' : ''}
      ${showSouvenirs ? '<button type="button" class="btn btn-secondary" data-action="souvenirs">Souvenirs</button>' : ''}
      ${showStorage ? '<button type="button" class="btn btn-secondary" data-action="storage">Stockage</button>' : ''}
      ${showGeocode ? '<button type="button" class="btn btn-secondary" data-action="geocode">Résoudre les lieux</button>' : ''}
      ${showTrash ? '<button type="button" class="btn btn-danger" data-action="empty-trash">Vider la corbeille</button>' : ''}
      <input type="file" accept="image/*" multiple data-upload-input hidden>
    `;
    if (showSouvenirs) {
      container
        .querySelector('[data-action="souvenirs"]')
        .addEventListener('click', () => this.router.navigate('/photos/souvenirs'));
    }
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
    if (showTrash) {
      container.querySelector('[data-action="empty-trash"]').addEventListener('click', async () => {
        if (!confirm('Supprimer définitivement TOUTES les photos de la corbeille ? Cette action est irréversible.')) return;
        try {
          const count = await emptyTrash();
          this._toast(`${count} photo(s) supprimée(s) définitivement`);
          await this._resetGrid();
        } catch (error) {
          this._toast(error.message || 'Erreur', 'error');
        }
      });
    }
    if (showStorage) {
      container
        .querySelector('[data-action="storage"]')
        .addEventListener('click', () => this._toggleStoragePanel());
    }
    if (showGeocode) {
      container
        .querySelector('[data-action="geocode"]')
        .addEventListener('click', () => this._startPlacesGeocode());
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
          this.timeline = 'days';
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

    // Sélecteur chronologique Années | Mois | Jours
    this.element.querySelectorAll('[data-tl]').forEach((btn) => {
      btn.addEventListener('click', () => this._setTimeline(btn.dataset.tl));
    });
    const tlBack = this.element.querySelector('[data-action="tl-back"]');
    if (tlBack) tlBack.addEventListener('click', () => this._timelineBack());

    // Date filter
    const yearSel = this.element.querySelector('[data-year]');
    const monthSel = this.element.querySelector('[data-month]');
    const clearDate = this.element.querySelector('[data-action="clear-date"]');
    if (yearSel && monthSel && clearDate) {
      this._populateYearSelect(yearSel);
      yearSel.addEventListener('change', async () => {
        const year = yearSel.value;
        if (year) {
          this._populateMonthSelect(monthSel, year);
          monthSel.disabled = false;
        } else {
          monthSel.value = '';
          monthSel.disabled = true;
        }
        this.dateFrom = year ? `${year}-01-01` : null;
        this.dateTo = year ? `${year}-12-31` : null;
        clearDate.hidden = !year;
        await this._resetGrid();
      });
      monthSel.addEventListener('change', async () => {
        const year = yearSel.value;
        const month = monthSel.value;
        if (year && month) {
          const start = `${year}-${month.padStart(2, '0')}-01`;
          const end = new Date(year, month, 0);
          this.dateFrom = start;
          this.dateTo = `${year}-${month.padStart(2, '0')}-${end.getDate()}`;
        } else if (year) {
          this.dateFrom = `${year}-01-01`;
          this.dateTo = `${year}-12-31`;
        } else {
          this.dateFrom = null;
          this.dateTo = null;
        }
        clearDate.hidden = !this.dateFrom;
        await this._resetGrid();
      });
      clearDate.addEventListener('click', async () => {
        yearSel.value = '';
        monthSel.value = '';
        monthSel.disabled = true;
        this.dateFrom = null;
        this.dateTo = null;
        clearDate.hidden = true;
        this.timeline = 'days';
        await this._resetGrid();
      });
    }

    // Bulk actions toolbar
    const bulkToolbar = this.element.querySelector('[data-bulk-toolbar]');
    if (bulkToolbar) {
      if (!this._bulkBound) {
        this._bulkBound = true;
        // Délégation : la grille est rendue après _bindToolbar()
        this.element.addEventListener('change', (event) => {
          const checkbox = event.target.closest?.('input[data-photo-id]');
          if (!checkbox) return;
          const id = Number(checkbox.dataset.photoId);
          if (checkbox.checked) {
            this.selectedPhotos.add(id);
          } else {
            this.selectedPhotos.delete(id);
          }
          const tile = checkbox.closest('[data-photo]');
          if (tile) tile.classList.toggle('selected', checkbox.checked);
          this._updateBulkToolbar();
        });
      }

      // Bulk favorite
      bulkToolbar.querySelector('[data-action="bulk-fav"]').addEventListener('click', async () => {
        if (!this._can('photos.update') || this.selectedPhotos.size === 0) return;
        const ids = Array.from(this.selectedPhotos);
        for (const id of ids) {
          const photo = this.photos.find((p) => p.id === id);
          if (!photo || photo.is_favorite) continue;
          try {
            await updatePhoto(id, { is_favorite: true });
            photo.is_favorite = true;
          } catch { /* ignore individual errors */ }
        }
        this.selectedPhotos.clear();
        this._updateBulkToolbar();
        this._renderGrid();
      });

      // Bulk delete
      bulkToolbar.querySelector('[data-action="bulk-delete"]').addEventListener('click', async () => {
        if (!this._can('photos.delete') || this.selectedPhotos.size === 0) return;
        const ids = Array.from(this.selectedPhotos);
        if (!confirm(`Supprimer ${ids.length} photo(s) ?`)) return;
        for (const id of ids) {
          try {
            await deletePhoto(id);
          } catch { /* ignore */ }
        }
        this.selectedPhotos.clear();
        this._updateBulkToolbar();
        await this._resetGrid();
      });

      // Cancel selection
      bulkToolbar.querySelector('[data-action="bulk-cancel"]').addEventListener('click', () => {
        this.selectedPhotos.clear();
        this._updateBulkToolbar();
        this._renderGrid();
      });

      this._updateBulkToolbar();
    }

    this._observeSentinel();
  }

  _observeSentinel() {
    const sentinel = this.element.querySelector('[data-sentinel]');
    if (!sentinel) {
      dbg('observeSentinel: sentinel ABSENT');
      return;
    }
    if (this.observer) this.observer.disconnect();
    this.observer = new IntersectionObserver((entries) => {
      entries.forEach((e) => dbg('sentinel intersecting=', e.isIntersecting,
        'photos=', this.photos.length, 'hasMore=', this.hasMore, 'loading=', this.loading));
      if (entries.some((e) => e.isIntersecting)) this._loadMore();
    }, { rootMargin: '10000px' });
    this.observer.observe(sentinel);
    dbg('observeSentinel: observer créé photos=', this.photos.length);
  }

  async _renderCards() {
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
          this.timeline = 'days';
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
          this.timeline = 'days';
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
      container.innerHTML = this.places.length
        ? '<div class="photos-places-map" data-places-map></div>'
        : '<p class="empty-message">Aucun lieu (photos sans GPS).</p>';
      container.hidden = Boolean(this.filter);
      grid.hidden = !this.filter;
      if (this.places.length && !this.filter) {
        await this._renderPlacesMap(container.querySelector('[data-places-map]'));
      }
    } else {
      container.innerHTML = '';
      container.hidden = true;
      grid.hidden = false;
    }
  }

  async _ensureLeaflet() {
    if (window.L) return;
    await new Promise((resolve, reject) => {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/vendor/leaflet/leaflet.css';
      document.head.appendChild(link);
      const script = document.createElement('script');
      script.src = '/vendor/leaflet/leaflet.js';
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  async _renderPlacesMap(el) {
    if (!el) return;
    await this._ensureLeaflet();
    if (this.placesMap) { this.placesMap.remove(); this.placesMap = null; }
    const map = window.L.map(el, { worldCopyJump: true }).setView([20, 0], 2);
    window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);
    for (const place of this.places) {
      if (!Number.isFinite(place.lat_cell) || !Number.isFinite(place.lon_cell)) continue;
      const name = place.label || `${place.lat_cell}, ${place.lon_cell}`;
      const countryLine = (place.country && place.country !== name)
        ? `<br>${this._esc(place.country)}` : '';

      let marker;
      const repPhotoId = place.representative_photo_id;
      if (repPhotoId) {
        const thumbUrl = photoFileUrl(repPhotoId, 'small');
        const icon = window.L.divIcon({
          className: 'photos-place-thumb-icon',
          html: `<img src="${thumbUrl}" alt="" style="width:48px;height:48px;object-fit:cover;border-radius:4px;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,.3);">`,
          iconSize: [48, 48],
          iconAnchor: [24, 48],
          popupAnchor: [0, -44],
        });
        marker = window.L.marker([place.lat_cell, place.lon_cell], { icon }).addTo(map);
      } else {
        const count = place.photo_count || 1;
        const radius = Math.min(20, 5 + Math.log10(count + 1) * 6);
        marker = window.L.circleMarker([place.lat_cell, place.lon_cell], {
          radius,
          color: '#2563eb',
          fillColor: '#2563eb',
          fillOpacity: 0.4,
          weight: 1,
        }).addTo(map);
      }
      marker.bindPopup(`<strong>${this._esc(name)}</strong>${countryLine}<br>${place.photo_count || 0} photo(s)`);
      marker.on('click', () => {
        this.filter = { type: 'place', id: place.id, name };
        this.timeline = 'days';
        this._rerender();
      });
    }
    this.placesMap = map;
  }

  // ------------------------------------- reverse-geocoding (opt-in backend)

  async _startPlacesGeocode() {
    try {
      const result = await geocodePlaces();
      this._toast(result.message || 'Résolution des lieux lancée');
      if (result.queued) this._pollPlacesGeocode();
    } catch (error) {
      this._toast(error.message || 'Erreur', 'error');
    }
  }

  // Le backend résout les lieux en arrière-plan (cadence ~1/s) : on
  // recharge la carte toutes les 3 s jusqu'à stabilisation (10 essais max).
  async _pollPlacesGeocode(attempts = 10) {
    this._stopPlacesGeocodePolling();
    for (let i = 0; i < attempts; i += 1) {
      await new Promise((resolve) => {
        this.placesGeocodePollHandle = setTimeout(resolve, 3000);
      });
      if (this.view !== 'places' || this.filter) return;
      try {
        const result = await listPlaces();
        this.places = result.items || [];
        const pending = this.places.filter((place) => !place.label).length;
        await this._rerender();
        if (!pending) {
          this._toast('Tous les lieux sont résolus');
          return;
        }
      } catch {
        return;
      }
    }
  }

  _stopPlacesGeocodePolling() {
    if (this.placesGeocodePollHandle) {
      clearTimeout(this.placesGeocodePollHandle);
      this.placesGeocodePollHandle = null;
    }
  }

  // Clé de groupe Jours : slice de la chaîne taken_at (heure locale naive,
  // aucun passage par Date → aucun décalage UTC).
  _dayKey(photo) {
    if (!photo.taken_at) return null;
    const s = String(photo.taken_at);
    return s.length >= 10 ? s.slice(0, 10) : null;
  }

  _dayLabel(key) {
    const parts = String(key).split('-');
    const y = Number(parts[0]); const m = Number(parts[1]); const d = Number(parts[2]);
    if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return key;
    const date = new Date(y, m - 1, d);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const diffDays = Math.round((date - today) / 86400000);
    if (diffDays === 0) return 'Aujourd\'hui';
    if (diffDays === -1) return 'Hier';
    const opts = { weekday: 'long', day: 'numeric', month: 'long' };
    if (y !== today.getFullYear()) opts.year = 'numeric';
    const label = date.toLocaleDateString('fr-FR', opts);
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  _monthLabelFromKey(key) {
    const parts = String(key).split('-');
    const y = Number(parts[0]); const m = Number(parts[1]);
    if (!Number.isFinite(y) || !Number.isFinite(m)) return key;
    const label = new Date(y, m - 1, 1).toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  // --- Portée chronologique (date_from / date_to réutilisés) ---------------

  _clearScope() {
    this.dateFrom = null;
    this.dateTo = null;
  }

  _setScope(year, month) {
    const y = Number(year);
    if (month) {
      const m = String(month).padStart(2, '0');
      const lastDay = new Date(y, Number(month), 0).getDate();
      this.dateFrom = `${y}-${m}-01`;
      this.dateTo = `${y}-${m}-${lastDay}`;
    } else {
      this.dateFrom = `${y}-01-01`;
      this.dateTo = `${y}-12-31`;
    }
  }

  _scopeYear() {
    return this.dateFrom ? Number(this.dateFrom.slice(0, 4)) : null;
  }

  _scopeIsFullYear() {
    return Boolean(this.dateFrom && this.dateTo
      && this.dateFrom.endsWith('-01-01')
      && this.dateTo.endsWith('-12-31')
      && this.dateFrom.slice(0, 4) === this.dateTo.slice(0, 4));
  }

  // --- Navigation Jours | Mois | Années ------------------------------------

  async _setTimeline(mode) {
    if (mode !== 'days' && mode !== 'months' && mode !== 'years') return;
    if (mode === this.timeline) return;
    if (mode === 'years') {
      this._clearScope();
    } else if (mode === 'months') {
      // Mois sans portée annuelle → restreindre à l'année en cours de scope.
      if (this.dateFrom && !this._scopeIsFullYear()) this._setScope(this._scopeYear());
    }
    this.timeline = mode;
    this._syncTimelineUi();
    this._syncDateSelects();
    await this._resetGrid();
  }

  async _timelineBack() {
    if (this.timeline === 'days') {
      const year = this._scopeYear();
      if (year) this._setScope(year);
      this.timeline = 'months';
    } else if (this.timeline === 'months') {
      this._clearScope();
      this.timeline = 'years';
    } else {
      return;
    }
    this._syncTimelineUi();
    this._syncDateSelects();
    await this._resetGrid();
  }

  async _openPeriod(key) {
    if (this.timeline === 'years') {
      this._setScope(Number(key));
      this.timeline = 'months';
    } else {
      const parts = String(key).split('-').map(Number);
      if (parts.length === 2 && Number.isFinite(parts[0]) && Number.isFinite(parts[1])) {
        this._setScope(parts[0], parts[1]);
      }
      this.timeline = 'days';
    }
    this._syncTimelineUi();
    this._syncDateSelects();
    await this._resetGrid();
  }

  _syncTimelineUi() {
    if (!this.element) return;
    // Masquer le sélecteur chronologique si un filtre est actif
    const tlContainer = this.element.querySelector('.photos-timeline');
    const back = this.element.querySelector('[data-action="tl-back"]');
    if (tlContainer) tlContainer.hidden = Boolean(this.filter);
    if (back) back.hidden = Boolean(this.filter) || !this.dateFrom || this.timeline === 'years';
    if (!back) return;
    if (!this.dateFrom || this.timeline === 'years') {
      back.hidden = true;
      back.textContent = '';
    } else if (this.timeline === 'months') {
      back.hidden = false;
      back.textContent = '← Années';
    } else {
      back.hidden = false;
      back.textContent = '← Mois';
    }
    this.element.querySelectorAll('[data-tl]').forEach((btn) => {
      const active = btn.dataset.tl === this.timeline;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }

  _syncDateSelects() {
    if (!this.element) return;
    const ySel = this.element.querySelector('[data-year]');
    const mSel = this.element.querySelector('[data-month]');
    const clearBtn = this.element.querySelector('[data-action="clear-date"]');
    if (!ySel || !mSel) return;
    const apply = () => {
      if (!this.dateFrom) {
        ySel.value = '';
        mSel.value = '';
        mSel.disabled = true;
        if (clearBtn) clearBtn.hidden = true;
        return;
      }
      const year = this.dateFrom.slice(0, 4);
      ySel.value = year;
      this._populateMonthSelect(mSel, year);
      mSel.disabled = false;
      const fullYear = this._scopeIsFullYear();
      mSel.value = fullYear ? '' : this.dateFrom.slice(5, 7);
      if (clearBtn) clearBtn.hidden = false;
    };
    apply();
    this._populateYearSelect(ySel).then(apply).catch(() => {});
  }

  _populateYearSelect(select) {
    if (select.dataset.populated) return Promise.resolve();
    return getTimeline({ interval: 'year' })
      .then((result) => {
        const years = (result.groups || []).map((g) => g.key);
        years.forEach((y) => {
          const opt = document.createElement('option');
          opt.value = y;
          opt.textContent = y;
          select.appendChild(opt);
        });
        select.dataset.populated = '1';
      })
      .catch(() => {});
  }

  _populateMonthSelect(select, year) {
    select.innerHTML = '<option value="">Tous les mois</option>';
    const months = [
      { v: '01', n: 'Janvier' }, { v: '02', n: 'Février' }, { v: '03', n: 'Mars' },
      { v: '04', n: 'Avril' }, { v: '05', n: 'Mai' }, { v: '06', n: 'Juin' },
      { v: '07', n: 'Juillet' }, { v: '08', n: 'Août' }, { v: '09', n: 'Septembre' },
      { v: '10', n: 'Octobre' }, { v: '11', n: 'Novembre' }, { v: '12', n: 'Décembre' }
    ];
    months.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.v;
      opt.textContent = m.n;
      select.appendChild(opt);
    });
  }

  _renderGrid() {
    if (this._isPeriodView()) {
      this._renderPeriods();
      return;
    }
    const grid = this.element.querySelector('[data-grid]');
    const empty = this.element.querySelector('[data-empty]');
    const count = this.element.querySelector('[data-count]');
    if (!grid) return;
    grid.className = 'photos-grid';
    if (count) count.textContent = this.photos.length ? `${this.photos.length} photo(s)` : '';
    if (empty) empty.hidden = this.photos.length > 0 || this.loading;
    const isTrash = this.view === 'trash';

    const fragments = [];
    let currentDay = null;
    this.photos.forEach((photo) => {
      const dayKey = this._dayKey(photo);
      if (dayKey !== currentDay) {
        currentDay = dayKey;
        if (dayKey) {
          fragments.push(`<div class="photos-day" data-day="${dayKey}">${this._esc(this._dayLabel(dayKey))}</div>`);
        }
      }
      fragments.push(this._tileHtml(photo, isTrash));
    });
    this._lastDayKey = currentDay;
    grid.innerHTML = fragments.join('');
    grid.querySelectorAll('[data-photo]').forEach((tile) => this._bindTile(tile, isTrash));
    this._observeSentinel();
  }

  // Append incrémental (pagination Jours) : on n'ajoute que les nouvelles
  // tuiles, sans reconstruire les N tuiles déjà affichées.
  _appendTiles(fromIndex) {
    const grid = this.element.querySelector('[data-grid]');
    const empty = this.element.querySelector('[data-empty]');
    const count = this.element.querySelector('[data-count]');
    if (!grid) return;
    if (count) count.textContent = this.photos.length ? `${this.photos.length} photo(s)` : '';
    if (empty) empty.hidden = this.photos.length > 0 || this.loading;
    const isTrash = this.view === 'trash';
    let html = '';
    for (let i = fromIndex; i < this.photos.length; i++) {
      const photo = this.photos[i];
      const dayKey = this._dayKey(photo);
      if (dayKey !== this._lastDayKey) {
        this._lastDayKey = dayKey;
        if (dayKey) {
          html += `<div class="photos-day" data-day="${dayKey}">${this._esc(this._dayLabel(dayKey))}</div>`;
        }
      }
      html += this._tileHtml(photo, isTrash);
    }
    if (!html) return;
    grid.insertAdjacentHTML('beforeend', html);
    const tiles = grid.querySelectorAll('[data-photo]');
    for (let i = fromIndex; i < tiles.length; i++) this._bindTile(tiles[i], isTrash);
  }

  _tileHtml(photo, isTrash) {
    const title = photo.title || photo.original_filename;
    const pending = photo.status !== 'ready';
    const analyzing = photo.analysis_status === 'pending' || photo.analysis_status === 'running';
    const analysisFailed = photo.analysis_status === 'failed';
    const isVideo = photo.mime_type?.startsWith('video/');
    const isSelected = this.selectedPhotos.has(photo.id);
    return `
        <div class="photos-tile ${pending ? 'is-pending' : ''}${isVideo ? ' is-video' : ''}${isSelected ? ' selected' : ''}" data-photo="${photo.id}" title="${this._esc(title)}">
          <label class="photos-tile-checkbox" title="Sélectionner">
            <input type="checkbox" data-photo-id="${photo.id}" ${isSelected ? 'checked' : ''}>
          </label>
          <img src="${photoFileUrl(photo.id, 'small')}" alt="${this._esc(title)}" loading="lazy">
          ${pending ? '<span class="photos-tile-status">…</span>' : ''}
          ${photo.status === 'failed' ? '<span class="photos-tile-status is-error">!</span>' : ''}
          ${analyzing ? '<span class="photos-tile-ai" title="Analyse IA en cours"></span>' : ''}
          ${analysisFailed ? '<span class="photos-tile-ai is-error" title="Analyse IA en échec"></span>' : ''}
          ${isVideo ? '<span class="photos-tile-video" title="Vidéo">▶</span>' : ''}
          ${isTrash ? `
            <button type="button" class="photos-tile-restore" data-restore="${photo.id}" title="Restaurer">↩</button>
            <button type="button" class="photos-tile-trash" data-trash="${photo.id}" title="Supprimer définitivement">🗑</button>
          ` : `
            <button type="button" class="photos-tile-fav ${photo.is_favorite ? 'is-on' : ''}"
                    data-fav="${photo.id}" title="Favori">★</button>
          `}
        </div>`;
  }

  _bindTile(tile, isTrash) {
    tile.addEventListener('click', (event) => {
      if (event.target.closest('[data-fav]')) return;
      if (event.target.closest('[data-restore]')) return;
      if (event.target.closest('[data-trash]')) return;
      if (event.target.closest('.photos-tile-checkbox')) return;
      this._openLightbox(Number(tile.dataset.photo));
    });
    const img = tile.querySelector('img');
    if (img) {
      img.addEventListener('error', () => tile.classList.add('is-nothumb'), { once: true });
    }
    if (!isTrash) {
      const btn = tile.querySelector('[data-fav]');
      if (btn) btn.addEventListener('click', async (event) => {
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
      return;
    }
    const restoreBtn = tile.querySelector('[data-restore]');
    if (restoreBtn) restoreBtn.addEventListener('click', async (event) => {
      event.stopPropagation();
      if (!this._can('photos.delete')) return;
      const id = Number(restoreBtn.dataset.restore);
      try {
        await restorePhoto(id);
        this._toast('Photo restaurée');
        await this._resetGrid();
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });
    const trashBtn = tile.querySelector('[data-trash]');
    if (trashBtn) trashBtn.addEventListener('click', async (event) => {
      event.stopPropagation();
      if (!this._can('photos.delete')) return;
      const id = Number(trashBtn.dataset.trash);
      if (!confirm('Supprimer définitivement cette photo ? L\'original NAS, les miniatures et retouches seront effacés.')) return;
      try {
        await hardDeletePhoto(id);
        this._toast('Photo supprimée définitivement');
        await this._resetGrid();
      } catch (error) {
        this._toast(error.message || 'Erreur', 'error');
      }
    });
  }

  // Vues Mois / Années : cartes agrégées (couverture + titre + comptage).
  _renderPeriods() {
    const grid = this.element.querySelector('[data-grid]');
    const empty = this.element.querySelector('[data-empty]');
    const count = this.element.querySelector('[data-count]');
    if (!grid) return;
    grid.className = 'photos-grid photos-grid--periods';
    if (count) count.textContent = this.periodTotal ? `${this.periodTotal} photo(s)` : '';
    if (empty) empty.hidden = this.periodGroups.length > 0;
    const isYears = this.timeline === 'years';
    grid.innerHTML = this.periodGroups.map((group) => {
      const label = isYears ? group.key : this._monthLabelFromKey(group.key);
      const cover = group.cover_photo_id
        ? `<img src="${photoFileUrl(group.cover_photo_id, 'medium')}" alt="" loading="lazy">`
        : '<span class="photos-period-noimg">–</span>';
      return `
      <button type="button" class="photos-period" data-period="${this._esc(group.key)}">
        <span class="photos-period-cover">${cover}</span>
        <span class="photos-period-title">${this._esc(label)}</span>
        <span class="photos-period-count">${group.count} photo(s)</span>
      </button>`;
    }).join('');
    grid.querySelectorAll('[data-period]').forEach((card) => {
      card.addEventListener('click', () => this._openPeriod(card.dataset.period));
      const img = card.querySelector('img');
      if (img) {
        img.addEventListener('error', () => card.classList.add('is-nothumb'), { once: true });
      }
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
        ${this._can('photos.delete') ? '<button type="button" class="btn btn-danger btn-sm" data-action="lb-delete">Supprimer</button>' : ''}
        ${detail.is_deleted ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-restore">Restaurer</button>' : ''}
        ${this._can('photos.analyze') ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-analyze">Analyser</button>' : ''}
        ${this._can('photos.analyze') ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-reindex">Ré-indexer</button>' : ''}
        ${this._can('photos.analyze') ? '<button type="button" class="btn btn-secondary btn-sm" data-action="lb-faces">Détecter visages</button>' : ''}
        <button type="button" class="btn btn-secondary btn-sm photos-lightbox-fav" data-action="lb-fav">
          ${detail.is_favorite ? '★ Retirer des favoris' : '☆ Ajouter aux favoris'}
        </button>
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
