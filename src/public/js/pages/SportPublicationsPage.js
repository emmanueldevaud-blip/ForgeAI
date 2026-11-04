import {
  listPublicationStyles,
  getPublicationSettings,
  updatePublicationSettings,
  listPublications,
  listRecentActivitiesForPublication,
  getPublicationForActivity,
  generatePublication,
  getPublication,
  updatePublication,
  validatePublication,
  markPublicationShared,
  generatePublicationCard,
  deletePublication,
  getInstagramConnectionStatus,
  connectInstagram,
  disconnectInstagram,
} from '../services/sportApi.js?v=9';
import { listPhotos, photoFileUrl } from '../services/photosApi.js?v=9';
import { authStore } from '../stores/auth.js';

const STYLES = [
  { code: 'humor', label: 'Humour et autodérision' },
  { code: 'stats', label: 'Statistiques et performance' },
  { code: 'motivation', label: 'Motivation et dépassement' },
  { code: 'inspiring', label: 'Inspirant et émotionnel' },
  { code: 'story', label: 'Récit de sortie' },
  { code: 'ultra', label: 'Esprit ultra-trail' },
  { code: 'short', label: 'Court et percutant' },
  { code: 'custom', label: 'Personnalisé' },
  { code: 'mix', label: 'Mix de styles' },
];

export class SportPublicationsPage {
  constructor() {
    this.element = null;
    this.settings = { notifications_enabled: true, last_styles: [], last_custom_instructions: null };
    this.stylesCatalog = {};
    this.recentActivities = [];
    this.publications = { draft: [], validated: [], shared: [] };
    this.tab = 'activities';
    this.selectedActivityId = null;
    this.selectedActivity = null;
    this.publication = null;
    this.selectedStyles = [];
    this.customInstructions = '';
    this.selectedPhotoId = null;
    this.photos = [];
    this.photosCursor = null;
    this.photosHasMore = false;
    this.proposals = [];
    this.selectedProposal = 0;
    this.editTitle = '';
    this.editContent = '';
    this.editHashtags = '';
    this.generating = false;
    this.saving = false;
    this.error = null;
    this.toastMsg = null;
    this.showPhotoPicker = false;
    this.loadingPhotos = false;
    this.instagramStatus = { connected: false, status: 'not_configured' };
  }

  async initialize() {
    try {
      const [settings, styles, recent, drafts, validated, shared] = await Promise.all([
        getPublicationSettings(),
        listPublicationStyles(),
        listRecentActivitiesForPublication(20),
        listPublications({ status: 'draft', page_size: 50 }),
        listPublications({ status: 'validated', page_size: 50 }),
        listPublications({ status: 'shared', page_size: 50 }),
      ]);
      this.settings = settings || this.settings;
      this.stylesCatalog = (styles && styles.styles) || {};
      this.recentActivities = (recent && recent.items) || [];
      this.publications.draft = (drafts && drafts.items) || [];
      this.publications.validated = (validated && validated.items) || [];
      this.publications.shared = (shared && shared.items) || [];
      // preselect last styles
      if (this.selectedStyles.length === 0 && this.settings.last_styles && this.settings.last_styles.length) {
        this.selectedStyles = [...this.settings.last_styles];
      }
      if (!this.customInstructions && this.settings.last_custom_instructions) {
        this.customInstructions = this.settings.last_custom_instructions;
      }
      try {
        this.instagramStatus = (await getInstagramConnectionStatus()) || this.instagramStatus;
      } catch (e) {
        this.instagramStatus = { connected: false, status: 'not_configured' };
      }
      if (typeof window !== 'undefined' && window.location.search.includes('connected=1')) {
        this._toast('Compte Instagram connecté avec succès !');
        try {
          const url = new URL(window.location.href);
          url.searchParams.delete('connected');
          window.history.replaceState({}, '', url.pathname + (url.search ? url.search : ''));
        } catch (_) {}
      }
    } catch (e) {
      this.error = e?.data?.detail || e?.message || 'Chargement impossible';
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content sport-publications';
    this.element.innerHTML = this._html();
    this._bind();
    return this.element;
  }

  _html() {
    if (this.selectedActivityId) return this._createHtml();
    return this._listHtml();
  }

  _listHtml() {
    const tabs = [
      { code: 'activities', label: 'Activités récentes' },
      { code: 'draft', label: `Brouillons (${this.publications.draft.length})` },
      { code: 'validated', label: `Validées (${this.publications.validated.length})` },
      { code: 'shared', label: `Partagées (${this.publications.shared.length})` },
    ];
    const tabsHtml = tabs.map(t => `<button class="btn ${this.tab === t.code ? 'btn-primary' : 'btn-secondary'} btn-sm" data-tab="${t.code}">${this._esc(t.label)}</button>`).join('');
    let body = '';
    if (this.tab === 'activities') {
      body = this.recentActivities.length ? this.recentActivities.map(a => this._activityRow(a)).join('') : '<p class="text-muted">Aucune activité récente.</p>';
    } else {
      const list = this.publications[this.tab] || [];
      body = list.length ? list.map(p => this._publicationRow(p)).join('') : '<p class="text-muted">Aucune publication.</p>';
    }

    let igLabel = 'Non connecté';
    let igBadgeStyle = 'color:var(--text-muted, #64748b);';
    if (this.instagramStatus && this.instagramStatus.connected) {
      const acct = this.instagramStatus.instagram_business_account_id ? ` (ID: ${this.instagramStatus.instagram_business_account_id})` : '';
      igLabel = `Connecté${acct}`;
      igBadgeStyle = 'color:#15803d;font-weight:600;';
    } else if (this.instagramStatus && this.instagramStatus.configured === false) {
      igLabel = 'Non configuré (Meta App requise)';
      igBadgeStyle = 'color:#b45309;font-weight:600;';
    }

    return `
      <div class="page-header"><div><h1>Mes publications</h1><p class="page-subtitle">Générez des publications Instagram à partir de vos activités.</p></div></div>
      <div class="card" style="margin-bottom:12px;">
        <div class="card-body" style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;">
          <strong>Instagram</strong>
          <span style="${igBadgeStyle}" data-ig-status>${this._esc(igLabel)}</span>
          <button class="btn btn-primary btn-sm" data-ig-connect>${this.instagramStatus && this.instagramStatus.connected ? 'Reconnecter' : 'Connecter Instagram'}</button>
          ${this.instagramStatus && this.instagramStatus.connected ? '<button class="btn btn-secondary btn-sm" data-ig-disconnect>Se déconnecter</button>' : ''}
        </div>
      </div>
      <div class="card" style="margin-bottom:12px;">
        <div class="card-body" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
          ${tabsHtml}
          <label style="margin-left:auto;display:flex;align-items:center;gap:6px;">
            <input type="checkbox" data-notif ${this.settings.notifications_enabled ? 'checked' : ''}> Notifications nouvelles activités
          </label>
        </div>
      </div>
      ${this.error ? `<div class="alert alert-danger" style="margin-bottom:12px;padding:8px 12px;border-radius:6px;background:#fee2e2;color:#991b1b;border:1px solid #f87171;">${this._esc(this.error)}</div>` : ''}
      ${this.toastMsg ? `<div class="alert alert-info" style="margin-bottom:12px;padding:8px 12px;border-radius:6px;background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;">${this._esc(this.toastMsg)}</div>` : ''}
      <div class="card"><div class="card-body">${body}</div></div>
    `;
  }

  async _loadInstagramStatus() {
    try {
      const status = await getInstagramConnectionStatus();
      this.instagramStatus = status || this.instagramStatus;
    } catch (e) {
      this.instagramStatus = { connected: false, status: 'not_configured' };
    }
    this._rerender();
  }

  async _connectInstagram() {
    const activity = this.selectedActivity || (this.recentActivities[0] || null);
    const athleteId = activity && activity.athlete_id ? activity.athlete_id : null;
    try {
      const data = await connectInstagram(athleteId);
      const url = data && data.authorize_url;
      if (url) {
        window.location.href = url;
      } else {
        this._toast('URL de connexion Meta non reçue');
      }
    } catch (e) {
      const msg = e?.data?.detail || e?.message || 'Connexion Instagram impossible';
      this._toast(msg);
    }
  }

  async _disconnectInstagram() {
    try {
      await disconnectInstagram();
      await this._loadInstagramStatus();
      this._toast('Instagram déconnecté');
    } catch (e) {
      this._toast(e?.data?.detail || 'Erreur lors de la déconnexion');
    }
  }

  _activityRow(a) {
    const dist = a.distance_m ? (a.distance_m / 1000).toFixed(1) + ' km' : '';
    const elev = a.elevation_gain_m ? `D+ ${Math.round(a.elevation_gain_m)} m` : '';
    const dur = a.duration_seconds ? this._duration(a.duration_seconds) : '';
    const date = a.started_at ? new Date(a.started_at).toLocaleDateString('fr-FR') : '';
    const existing = this.publications.draft.concat(this.publications.validated, this.publications.shared).find(p => p.activity_id === a.id);
    const badge = existing ? `<span class="status-badge">${existing.status}</span>` : '';
    return `
      <div class="card" style="margin-bottom:8px;">
        <div class="card-body" style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
          <div>
            <strong>${this._esc(a.activity_name || a.sport_type)}</strong> ${badge}
            <div class="text-muted" style="font-size:13px;">${this._esc(date)} · ${this._esc(a.sport_type)} · ${this._esc(dist)} ${this._esc(elev)} ${this._esc(dur)}</div>
          </div>
          <button class="btn btn-primary btn-sm" data-generate="${a.id}">Générer une publication</button>
        </div>
      </div>
    `;
  }

  _publicationRow(p) {
    const title = p.title || '(sans titre)';
    const preview = (p.content || '').slice(0, 120);
    const date = p.created_at ? new Date(p.created_at).toLocaleDateString('fr-FR') : '';
    return `
      <div class="card" style="margin-bottom:8px;">
        <div class="card-body">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
            <strong>${this._esc(title)}</strong>
            <span class="text-muted" style="font-size:12px;">${this._esc(date)}</span>
          </div>
          <p class="text-muted" style="font-size:13px;margin:6px 0;">${this._esc(preview)}${(p.content||'').length>120?'…':''}</p>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <button class="btn btn-secondary btn-sm" data-open="${p.id}">Ouvrir</button>
            ${p.status !== 'shared' ? `<button class="btn btn-secondary btn-sm" data-delete="${p.id}">Supprimer</button>` : ''}
          </div>
        </div>
      </div>
    `;
  }

  _createHtml() {
    const a = this.selectedActivity;
    const stylesHtml = STYLES.map(s => `
      <label style="display:flex;align-items:center;gap:6px;margin:2px 0;">
        <input type="checkbox" data-style="${s.code}" ${this.selectedStyles.includes(s.code) ? 'checked' : ''}> ${this._esc(s.label)}
      </label>
    `).join('');
    const customVisible = this.selectedStyles.includes('custom');
    const photoPreview = this.selectedPhotoId ? `<img src="${photoFileUrl(this.selectedPhotoId, 'medium')}" style="max-width:100%;border-radius:8px;">` : (this.publication && this.publication.card_path ? `<p class="text-muted">Carte générée</p>` : '<p class="text-muted">Aucune photo sélectionnée.</p>');
    const proposalsHtml = this.proposals.length ? this.proposals.map((p, i) => `
      <div class="card" style="margin-bottom:8px;${i===this.selectedProposal?'border:2px solid var(--color-primary);':''}">
        <div class="card-body">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <strong>Proposition ${i + 1}</strong>
            <button class="btn btn-secondary btn-sm" data-select-prop="${i}">Choisir</button>
          </div>
          ${p.title ? `<p><strong>${this._esc(p.title)}</strong></p>` : ''}
          <p style="white-space:pre-wrap;">${this._esc(p.content || '')}</p>
          ${p.hashtags ? `<p class="text-muted" style="font-size:13px;">${this._esc(p.hashtags)}</p>` : ''}
        </div>
      </div>
    `).join('') : (this.generating ? '<p class="text-muted">Génération en cours…</p>' : '<p class="text-muted">Aucune proposition. Cliquez sur « Générer ».</p>');

    const activitySummary = a ? `
      <div class="card" style="margin-bottom:12px;"><div class="card-body">
        <strong>${this._esc(a.activity_name || a.sport_type)}</strong>
        <div class="text-muted" style="font-size:13px;">
          ${a.started_at ? new Date(a.started_at).toLocaleString('fr-FR') : ''} · ${this._esc(a.sport_type)}
          ${a.distance_m ? ' · ' + (a.distance_m/1000).toFixed(1) + ' km' : ''}
          ${a.elevation_gain_m ? ' · D+ ' + Math.round(a.elevation_gain_m) + ' m' : ''}
          ${a.duration_seconds ? ' · ' + this._duration(a.duration_seconds) : ''}
          ${a.avg_heart_rate ? ' · FC ' + Math.round(a.avg_heart_rate) + ' bpm' : ''}
          ${a.calories ? ' · ' + Math.round(a.calories) + ' kcal' : ''}
        </div>
      </div></div>
    ` : '';

    return `
      <div class="page-header"><div><h1>Créer une publication</h1><p class="page-subtitle">${a ? this._esc(a.activity_name || a.sport_type) : ''}</p></div>
        <button class="btn btn-secondary btn-sm" data-back>← Retour</button>
      </div>
      ${activitySummary}
      ${this.error ? `<p class="text-danger">${this._esc(this.error)}</p>` : ''}
      ${this.toastMsg ? `<p class="text-success">${this._esc(this.toastMsg)}</p>` : ''}

      <div class="card" style="margin-bottom:12px;"><div class="card-body">
        <h3>Ton rédactionnel</h3>
        ${stylesHtml}
        ${customVisible ? `<textarea class="form-control" data-custom rows="3" placeholder="Consignes personnalisées…" style="margin-top:8px;">${this._esc(this.customInstructions)}</textarea>` : ''}
        <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-primary btn-sm" data-generate ${this.generating ? 'disabled' : ''}>${this.generating ? 'Génération…' : 'Générer 3 propositions'}</button>
          ${this.proposals.length ? `<button class="btn btn-secondary btn-sm" data-regenerate ${this.generating ? 'disabled' : ''}>Régénérer</button>` : ''}
        </div>
      </div></div>

      <div class="card" style="margin-bottom:12px;"><div class="card-body">
        <h3>Photo / visuel</h3>
        ${photoPreview}
        <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-secondary btn-sm" data-pick-photo>Choisir une photo</button>
          <button class="btn btn-secondary btn-sm" data-gen-card>Générer une carte stats</button>
          ${this.selectedPhotoId ? `<button class="btn btn-secondary btn-sm" data-clear-photo>Retirer</button>` : ''}
        </div>
      </div></div>

      <div class="card" style="margin-bottom:12px;"><div class="card-body">
        <h3>Propositions IA</h3>
        ${proposalsHtml}
      </div></div>

      <div class="card" style="margin-bottom:12px;"><div class="card-body">
        <h3>Éditeur</h3>
        <label>Titre / accroche<input class="form-control" data-title value="${this._esc(this.editTitle)}"></label>
        <label style="margin-top:8px;">Texte<textarea class="form-control" data-content rows="6">${this._esc(this.editContent)}</textarea></label>
        <label style="margin-top:8px;">Hashtags<textarea class="form-control" data-hashtags rows="2">${this._esc(this.editHashtags)}</textarea></label>
      </div></div>

      <div class="card" style="margin-bottom:12px;"><div class="card-body">
        <h3>Prévisualisation Instagram</h3>
        <div style="max-width:360px;border:1px solid var(--color-border-light);border-radius:12px;padding:12px;background:#fff;">
          ${this.selectedPhotoId ? `<img src="${photoFileUrl(this.selectedPhotoId, 'medium')}" style="width:100%;border-radius:8px;margin-bottom:8px;">` : ''}
          <p style="white-space:pre-wrap;margin:0;">${this._esc(this.editTitle ? this.editTitle + '\n\n' : '')}${this._esc(this.editContent)}</p>
          ${this.editHashtags ? `<p style="color:#00376b;margin-top:8px;">${this._esc(this.editHashtags)}</p>` : ''}
        </div>
      </div></div>

      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn btn-primary" data-save ${this.saving ? 'disabled' : ''}>Enregistrer le brouillon</button>
        <button class="btn btn-primary" data-validate ${this.saving ? 'disabled' : ''}>Valider</button>
        <button class="btn btn-secondary" data-copy>Copier le texte</button>
        <button class="btn btn-secondary" data-open-ig>Ouvrir Instagram</button>
        ${this.publication && this.publication.status !== 'shared' ? `<button class="btn btn-secondary" data-mark-shared>J'ai partagé</button>` : ''}
      </div>

      ${this.showPhotoPicker ? this._photoPickerHtml() : ''}
    `;
  }

  _photoPickerHtml() {
    const tiles = this.photos.map(p => `
      <div class="photos-tile" data-pick="${p.id}" style="cursor:pointer;">
        <img src="${photoFileUrl(p.id, 'small')}" loading="lazy" style="width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;">
      </div>
    `).join('');
    return `
      <div class="modal-overlay" data-photo-modal style="position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;display:flex;align-items:center;justify-content:center;">
        <div class="modal" style="background:#fff;max-width:720px;width:90%;max-height:80vh;overflow:auto;padding:16px;border-radius:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <h3>Choisir une photo</h3>
            <button class="btn btn-secondary btn-sm" data-close-picker>Fermer</button>
          </div>
          ${this.loadingPhotos ? '<p class="text-muted">Chargement…</p>' : ''}
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">${tiles}</div>
          ${this.photosHasMore ? '<div style="text-align:center;margin-top:8px;"><button class="btn btn-secondary btn-sm" data-load-more-photos>Charger plus</button></div>' : ''}
        </div>
      </div>
    `;
  }

  _bind() {
    if (this.selectedActivityId) this._bindCreate(); else this._bindList();
  }

  _bindList() {
    this.element.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { this.tab = b.dataset.tab; this._rerender(); }));
    this.element.querySelector('[data-notif]')?.addEventListener('change', async (e) => {
      this.settings.notifications_enabled = e.target.checked;
      try { await updatePublicationSettings({ notifications_enabled: e.target.checked }); } catch (err) { this._toast(err?.data?.detail || 'Erreur'); }
    });
    const igConnect = this.element.querySelector('[data-ig-connect]');
    const igDisconnect = this.element.querySelector('[data-ig-disconnect]');
    if (igConnect) igConnect.addEventListener('click', async () => { await this._connectInstagram(); });
    if (igDisconnect) igDisconnect.addEventListener('click', async () => { await this._disconnectInstagram(); });
    this.element.querySelectorAll('[data-generate]').forEach(b => b.addEventListener('click', async () => {
      const id = Number(b.dataset.generate);
      await this._openCreate(id);
    }));
    this.element.querySelectorAll('[data-open]').forEach(b => b.addEventListener('click', async () => {
      const id = Number(b.dataset.open);
      const pub = await getPublication(id).catch(() => null);
      if (pub) await this._openFromPublication(pub);
    }));
    this.element.querySelectorAll('[data-delete]').forEach(b => b.addEventListener('click', async () => {
      const id = Number(b.dataset.delete);
      if (!window.confirm('Supprimer cette publication ?')) return;
      try { await deletePublication(id); this._toast('Supprimée'); await this.initialize(); this._rerender(); } catch (e) { this._toast(e?.data?.detail || 'Erreur'); }
    }));
  }

  async _openCreate(activityId) {
    this.selectedActivityId = activityId;
    this.selectedActivity = this.recentActivities.find(a => a.id === activityId) || null;
    if (!this.selectedActivity) {
      try {
        const res = await listRecentActivitiesForPublication(50);
        this.selectedActivity = (res.items || []).find(a => a.id === activityId) || null;
        this.recentActivities = res.items || this.recentActivities;
      } catch (e) {}
    }
    this.publication = null;
    this.proposals = [];
    this.selectedProposal = 0;
    this.editTitle = '';
    this.editContent = '';
    this.editHashtags = '';
    this.selectedPhotoId = null;
    this.error = null;
    this.toastMsg = null;
    // si publication existante pour cette activite, la charger
    try {
      const pub = await getPublicationForActivity(activityId);
      this.publication = pub;
      this.selectedStyles = pub.styles || this.selectedStyles;
      this.customInstructions = pub.custom_instructions || this.customInstructions;
      this.selectedPhotoId = pub.photo_id || null;
      this.proposals = pub.proposals || [];
      this.selectedProposal = pub.selected_proposal || 0;
      this.editTitle = pub.title || '';
      this.editContent = pub.content || '';
      this.editHashtags = pub.hashtags || '';
    } catch (e) {
      // 404 ok
    }
    this._rerender();
  }

  async _openFromPublication(pub) {
    await this._openCreate(pub.activity_id);
  }

  _bindCreate() {
    this.element.querySelectorAll('[data-style]').forEach(cb => {
      cb.addEventListener('change', () => {
        const code = cb.dataset.style;
        if (cb.checked) { if (!this.selectedStyles.includes(code)) this.selectedStyles.push(code); }
        else { this.selectedStyles = this.selectedStyles.filter(s => s !== code); }
        this._rerender();
      });
    });
    const customTa = this.element.querySelector('[data-custom]');
    if (customTa) customTa.addEventListener('input', (e) => { this.customInstructions = e.target.value; });
    this.element.querySelector('[data-back]')?.addEventListener('click', () => { this.selectedActivityId = null; this.selectedActivity = null; this._rerender(); });
    this.element.querySelector('[data-generate]')?.addEventListener('click', () => this._generate(false));
    this.element.querySelector('[data-regenerate]')?.addEventListener('click', () => this._generate(true));
    this.element.querySelector('[data-pick-photo]')?.addEventListener('click', async () => {
      this.showPhotoPicker = true;
      this.photos = [];
      this.photosCursor = null;
      this.photosHasMore = false;
      this.loadingPhotos = true;
      this._rerender();
      try {
        const res = await listPhotos({ page_size: 60 });
        this.photos = res.items || [];
        this.photosCursor = res.next_cursor || null;
        this.photosHasMore = !!res.next_cursor;
      } catch (e) { this._toast(e?.data?.detail || 'Erreur photos'); }
      this.loadingPhotos = false;
      this._rerender();
    });
    this.element.querySelector('[data-close-picker]')?.addEventListener('click', () => { this.showPhotoPicker = false; this._rerender(); });
    this.element.querySelector('[data-photo-modal]')?.addEventListener('click', (e) => {
      if (e.target.dataset.photoModal !== undefined && e.target === e.currentTarget) { this.showPhotoPicker = false; this._rerender(); }
    });
    this.element.querySelectorAll('[data-pick]').forEach(t => t.addEventListener('click', () => {
      this.selectedPhotoId = Number(t.dataset.pick);
      this.showPhotoPicker = false;
      this._rerender();
    }));
    this.element.querySelector('[data-load-more-photos]')?.addEventListener('click', async () => {
      if (!this.photosCursor) return;
      this.loadingPhotos = true; this._rerender();
      try {
        const res = await listPhotos({ page_size: 60, cursor: this.photosCursor });
        this.photos = this.photos.concat(res.items || []);
        this.photosCursor = res.next_cursor || null;
        this.photosHasMore = !!res.next_cursor;
      } catch (e) {}
      this.loadingPhotos = false; this._rerender();
    });
    this.element.querySelector('[data-clear-photo]')?.addEventListener('click', () => { this.selectedPhotoId = null; this._rerender(); });
    this.element.querySelector('[data-gen-card]')?.addEventListener('click', async () => {
      if (!this.publication) { this._toast('Enregistrez d\'abord un brouillon'); return; }
      try {
        const res = await generatePublicationCard(this.publication.id);
        this.publication.card_path = res.card_path;
        this.publication.visual_type = 'card';
        this._toast('Carte générée');
        this._rerender();
      } catch (e) { this._toast(e?.data?.detail || 'Erreur carte'); }
    });
    this.element.querySelectorAll('[data-select-prop]').forEach(b => b.addEventListener('click', () => {
      const idx = Number(b.dataset.selectProp);
      this.selectedProposal = idx;
      const p = this.proposals[idx];
      if (p) { this.editTitle = p.title || ''; this.editContent = p.content || ''; this.editHashtags = p.hashtags || ''; }
      this._rerender();
    }));
    const titleIn = this.element.querySelector('[data-title]');
    if (titleIn) titleIn.addEventListener('input', (e) => { this.editTitle = e.target.value; });
    const contentIn = this.element.querySelector('[data-content]');
    if (contentIn) contentIn.addEventListener('input', (e) => { this.editContent = e.target.value; });
    const hashIn = this.element.querySelector('[data-hashtags]');
    if (hashIn) hashIn.addEventListener('input', (e) => { this.editHashtags = e.target.value; });

    this.element.querySelector('[data-save]')?.addEventListener('click', () => this._save(false));
    this.element.querySelector('[data-validate]')?.addEventListener('click', () => this._save(true));
    this.element.querySelector('[data-copy]')?.addEventListener('click', async () => {
      const text = `${this.editTitle ? this.editTitle + '\n\n' : ''}${this.editContent}${this.editHashtags ? '\n\n' + this.editHashtags : ''}`;
      try { await navigator.clipboard.writeText(text); this._toast('Texte copié'); } catch (e) { this._toast('Copie impossible'); }
    });
    this.element.querySelector('[data-open-ig]')?.addEventListener('click', () => {
      window.open('https://www.instagram.com/', '_blank');
    });
    this.element.querySelector('[data-mark-shared]')?.addEventListener('click', async () => {
      if (!this.publication) return;
      try { await markPublicationShared(this.publication.id); this._toast('Marquée partagée'); await this.initialize(); this.selectedActivityId = null; this._rerender(); } catch (e) { this._toast(e?.data?.detail || 'Erreur'); }
    });
  }

  async _generate(regenerate) {
    if (!this.selectedActivityId) return;
    if (!this.selectedStyles.length) { this._toast('Sélectionnez au moins un ton'); return; }
    this.generating = true;
    this.error = null;
    this._rerender();
    try {
      const data = {
        styles: this.selectedStyles,
        custom_instructions: this.selectedStyles.includes('custom') ? (this.customInstructions || null) : null,
        regenerate: !!regenerate,
      };
      const pub = await generatePublication(this.selectedActivityId, data);
      this.publication = pub;
      this.proposals = pub.proposals || [];
      this.selectedProposal = pub.selected_proposal || 0;
      if (this.proposals.length && this.proposals[0]) {
        this.editTitle = this.proposals[0].title || '';
        this.editContent = this.proposals[0].content || '';
        this.editHashtags = this.proposals[0].hashtags || '';
      }
      this.selectedPhotoId = pub.photo_id || this.selectedPhotoId;
      // persist last styles
      try { await updatePublicationSettings({ last_styles: this.selectedStyles, last_custom_instructions: data.custom_instructions }); } catch (e) {}
      this._toast('Propositions générées');
    } catch (e) {
      this.error = e?.data?.detail || e?.message || 'Génération impossible';
    } finally {
      this.generating = false;
      this._rerender();
    }
  }

  async _save(validate) {
    if (!this.publication) {
      // create draft by generating? require at least content
      if (!this.editContent.trim()) { this._toast('Texte vide'); return; }
      // no publication yet: generate first? We'll require generation first
      this._toast('Générez d\'abord des propositions');
      return;
    }
    this.saving = true;
    this._rerender();
    try {
      await updatePublication(this.publication.id, {
        title: this.editTitle || null,
        content: this.editContent,
        hashtags: this.editHashtags || null,
        photo_id: this.selectedPhotoId,
        selected_proposal: this.selectedProposal,
        styles: this.selectedStyles,
        custom_instructions: this.selectedStyles.includes('custom') ? (this.customInstructions || null) : null,
      });
      if (validate) {
        await validatePublication(this.publication.id);
        this._toast('Publication validée');
      } else {
        this._toast('Brouillon enregistré');
      }
      await this.initialize();
      // reload publication
      this.publication = await getPublication(this.publication.id);
    } catch (e) {
      this.error = e?.data?.detail || e?.message || 'Enregistrement impossible';
    } finally {
      this.saving = false;
      this._rerender();
    }
  }

  _rerender() {
    const parent = this.element?.parentElement;
    if (!parent) return;
    const old = this.element;
    const rendered = this.render();
    parent.replaceChild(rendered, old);
  }

  _toast(msg) { this.toastMsg = msg; this._rerender(); setTimeout(() => { this.toastMsg = null; this._rerender(); }, 2500); }

  _duration(s) {
    const h = Math.floor(s / 3600); const m = Math.floor((s % 3600) / 60);
    return h ? `${h}h${String(m).padStart(2, '0')}` : `${m} min`;
  }

  _esc(v) { const d = document.createElement('div'); d.textContent = v == null ? '' : String(v); return d.innerHTML; }
}

export function createSportPublicationsPage(router) { return new SportPublicationsPage(); }