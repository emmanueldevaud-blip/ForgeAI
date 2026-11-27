/**
 * CommunityPublisherPage — Point d'entrée unique pour la création
 * Publication, Carrousel, Reel, Story — Interface unifiée style Instagram
 *
 * Chrome unifié :
 *   - header (retour + sélecteur de format + sauvegarde) : masqué sur `media`
 *     (le sélecteur de médias possède son propre header) et sur `compose`
 *     (l'éditeur imbriqué possède le sien)
 *   - barre de progression segmentée : masquée avec le header
 *   - footer unique Précédent/Suivant : masqué sur `media` et sur `publish`
 *     (le CTA y est `publish-final` dans le contenu)
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js?v=3';
import { getSuggestedPhotosForActivity } from '../services/sportApi.js?v=16';
import { createPublisherMediaPicker } from '../components/PublisherMediaPicker.js?v=2';
import { createPublisherCaptionEditor } from '../components/PublisherCaptionEditor.js?v=2';
import { createPublisherPreview } from '../components/PublisherPreview.js?v=4';
import { createPublisherMusicStep } from '../components/PublisherMusicStep.js?v=1';
import { createPublisherPostEditor } from '../editors/PublisherPostEditor.js?v=3';
import { createPublisherReelEditor } from '../editors/PublisherReelEditor.js';
import { createPublisherStoryEditor } from '../editors/PublisherStoryEditor.js?v=5';
import { storySlidesReady } from '../services/storyPublishPipeline.js';

/**
 * Métadonnées des étapes (libellé + icône).
 */
const STEP_META = {
  media: { label: 'Médias', icon: '📷' },
  adjust: { label: 'Ajuster', icon: '✂️' },
  compose: { label: 'Composer', icon: '✨' },
  music: { label: 'Musique', icon: '🎵' },
  caption: { label: 'Légende', icon: '📝' },
  preview: { label: 'Aperçu', icon: '👁️' },
  publish: { label: 'Publier', icon: '🚀' },
};

/**
 * Configuration unique des formats.
 *
 * Copie locale alignée sur `FORMAT_CONFIG` de `stores/publisherStore.js` :
 * les tests frontend suppriment les imports du module, la table doit donc
 * rester déclarée ici. Modifier les deux ensemblages ensemble.
 */
const FORMAT_CONFIG = {
  post: {
    label: 'Publication',
    icon: '📸',
    steps: ['media', 'adjust', 'caption', 'preview', 'publish'],
    maxMedia: 1,
    minMedia: 1,
    allowedTypes: ['photo'],
  },
  carousel: {
    label: 'Carrousel',
    icon: '🖼️',
    steps: ['media', 'adjust', 'caption', 'preview', 'publish'],
    maxMedia: 10,
    minMedia: 2,
    allowedTypes: ['photo'],
  },
  reel: {
    label: 'Reel',
    icon: '🎬',
    steps: ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'],
    maxMedia: 20,
    minMedia: 1,
    allowedTypes: ['photo', 'video'],
  },
  story: {
    label: 'Story',
    icon: '📖',
    steps: ['media', 'adjust', 'compose', 'music', 'caption', 'preview', 'publish'],
    maxMedia: 10,
    minMedia: 1,
    allowedTypes: ['photo'],
  },
};

const CAPTION_MAX_LENGTH = 2200;

export class CommunityPublisherPage {
  constructor(router, options = {}) {
    this.router = router;
    this.entryId = options.entryId || null;
    this.format = FORMAT_CONFIG[options.format] ? options.format : 'post';
    this.garminActivityId = options.garminActivityId || null;
    this.preselectedMedia = options.preselectedMedia || [];
    this.freshDraft = !!options.freshDraft;
    this.onBack = options.onBack || null;
    this.isExistingPublication = options.isExistingPublication || false;

    this.element = null;
    this.mediaPicker = null;
    this.captionEditor = null;
    this.preview = null;
    this.formatEditor = null; // Post/Reel/Story editor
    this.adjustEditor = null; // PublisherPostEditor (recadrage / réorganisation)
    this.musicStep = null; // Étape Musique (Story)
    this.currentStep = 'media';
    this.loading = false;
    this.error = null;
    this._renderedStep = null;
    this._unsubscribeStore = null;
    this._garminListener = null;
    this._navLocked = false;
    this._mediaRestored = false;
    this._subscribeStore();
  }

  async initialize() {
    // Charger le brouillon existant ou en créer un nouveau
    if (this.isExistingPublication) {
      await this._loadExistingPublication(this.entryId);
    } else if (this.entryId) {
      await this._loadFromCalendarEntry();
    } else if (this.garminActivityId) {
      await this._loadFromGarmin();
    } else if (this.freshDraft) {
      await publisherDraftService.createBlank(this.format);
    } else {
      await this._restoreOrResetDraft();
    }

    // Appliquer les médias pré-sélectionnés
    if (this.preselectedMedia.length) {
      publisherStore.draft.media = this.preselectedMedia.map((m, i) => ({
        ...m,
        id: String(m.id ?? `media_${Date.now()}_${i}`),
        photoId: m.photoId ?? m.id,
        order: i,
      }));
      publisherStore._notify();
    }
  }

  /**
   * Reprend le brouillon local persisté s'il contient des données,
   * sinon en crée un propre pour le format demandé.
   * Ne jamais écraser un brouillon en cours.
   */
  async _restoreOrResetDraft() {
    const draft = publisherStore.draft;
    const caption = draft.caption || {};
    const hasData = (draft.media && draft.media.length > 0)
      || !!(caption.title || caption.content || caption.hashtags)
      || !!(draft.design && Object.keys(draft.design).length > 0);

    if (!hasData) {
      // Nouveau brouillon : créer un brouillon serveur standalone (Lot 0 A01).
      // Le store local est réinitialisé puis le contenu sauvegardé dessus via
      // la création serveur déjà liée au service.
      await publisherDraftService.createBlank(this.format);
    } else if (draft.format !== this.format) {
      publisherStore.setFormat(this.format);
      // Le format conditionne la sélection : limiter le nombre et les types
      // de médias autorisés pour le nouveau format.
      this._enforceFormatLimits();
    } else {
      // Simule une notification pour resynchroniser la page sur l'état restauré
      publisherStore._notify();
    }
  }

  /**
   * Le format de publication conditionne la sélection : le nombre de médias
   * et leurs types doivent respecter les limites du format courant
   * (ex : un Carrousel peut contenir 10 photos, une Publication 1).
   */
  _enforceFormatLimits() {
    const format = publisherStore.draft.format;
    const config = FORMAT_CONFIG[format] || FORMAT_CONFIG.post;
    const media = publisherStore.draft.media || [];
    const kept = media
      .filter((m) => config.allowedTypes.includes(m.type === 'video' ? 'video' : 'photo'))
      .slice(0, config.maxMedia)
      .map((m, i) => ({ ...m, order: i }));
    if (kept.length === media.length) return;
    publisherStore.draft.media = kept;
    publisherStore.draft.updatedAt = Date.now();
    publisherStore._notify();
  }

  async _loadFromCalendarEntry() {
    try {
      const visualType = this.format === 'carousel' ? 'carousel'
        : this.format === 'reel' ? 'reel'
          : 'photo';
      await publisherDraftService.createFromCalendar({
        calendarEntryId: this.entryId,
        format: this.format,
        visualType,
      });
      // Le service met à jour le store
    } catch (error) {
      this.error = error.message;
    }
  }

  async _loadFromGarmin() {
    // Pour l'instant, on attend la sélection de photos via le MediaPicker
    // Le MediaPicker émettra un événement pmp:garmin-select
    publisherStore.setGarmin(this.garminActivityId, {}, []);

    // Lot 0 (A03) : charger les photos suggérées pour l'activité Garmin au lieu
    // d'ignorer le résultat — la sélection part des suggestions de l'activité.
    const format = this.format;
    const maxMedia = (FORMAT_CONFIG[format] || FORMAT_CONFIG.post).maxMedia || 10;
    try {
      const photos = await getSuggestedPhotosForActivity(this.garminActivityId, maxMedia);
      const items = Array.isArray(photos) ? photos : (photos?.items || []);
      const currentMedia = publisherStore.draft.media || [];
      const existing = new Set(currentMedia.map(
        m => String(m.photoId ?? String(m.id).replace(/^photo_/, '')),
      ));
      const remaining = Math.max(0, maxMedia - currentMedia.length);
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
      if (toAdd.length) publisherStore.addMedia(toAdd);
    } catch (error) {
      console.warn('[Publisher] Suggestions Garmin indisponibles :', error?.message || error);
    }
  }

  async _loadExistingPublication(publicationId) {
    try {
      await publisherDraftService.load(
        publicationId,
        this.format === 'story' ? 'story' : null,
      );
      // Le service met à jour le store
      // Rafraîchir le media picker si on est sur l'étape media
      if (this.currentStep === 'media' && this.mediaPicker) {
        this.mediaPicker._updateSelectionUI();
        this.mediaPicker._updateCounter();
        this.mediaPicker._updateGridSelection();
      }
    } catch (error) {
      this.error = error.message;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'publisher-page';
    }
    if (this.element.children.length === 0) {
      this.element.innerHTML = this._renderShell();
      this._bindEvents();
      this._renderStep();
      this._updateChrome();
      this._updateStepIndicator();
      this._updateFooterButtons();
    }
    return this.element;
  }

  mount(host) {
    if (!this.element) this.render();
    host.appendChild(this.element);

    // Écouter les événements Garmin du MediaPicker
    this._garminListener = (e) => this._onGarminSelect(e.detail.activityId);
    this.element.addEventListener('pmp:garmin-select', this._garminListener);
  }

  _subscribeStore() {
    if (this._unsubscribeStore) return;
    this._unsubscribeStore = publisherStore.subscribe(state => {
      this.format = FORMAT_CONFIG[state.draft.format] ? state.draft.format : 'post';
      this.currentStep = state.ui.currentStep;
      this._updateStepContent();
    });
  }

  _renderShell() {
    const config = FORMAT_CONFIG[this.format];
    const canSwitchFormat = !this.entryId && !this.isExistingPublication;
    return `
      <header class="publisher-header">
        <div class="publisher-header-bar">
          <div class="publisher-header-left">
            <button type="button" class="publisher-btn publisher-btn-back" data-action="back" aria-label="Retour">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
              </svg>
            </button>
            ${canSwitchFormat ? `
              <div class="publisher-format" data-format-root>
                <button type="button" class="publisher-format-btn" data-action="select-format" aria-haspopup="menu" aria-expanded="false">
                  <span class="publisher-format-icon">${config.icon}</span>
                  <span class="publisher-format-label">${config.label}</span>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
                <div class="publisher-format-menu" data-format-menu hidden role="menu">
                  ${Object.entries(FORMAT_CONFIG).map(([key, c]) => `
                    <button type="button" role="menuitem" class="publisher-format-option ${key === this.format ? 'active' : ''}" data-format="${key}">
                      <span class="publisher-format-icon">${c.icon}</span>
                      <span>${c.label}</span>
                    </button>
                  `).join('')}
                </div>
              </div>
            ` : `
              <h1 class="publisher-header-title">
                <span class="publisher-format-icon">${config.icon}</span>
                <span class="publisher-format-label">${config.label}</span>
              </h1>
            `}
          </div>
          <div class="publisher-header-right">
            <button type="button" class="publisher-btn publisher-btn-secondary" data-action="save-draft">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/></svg>
              <span class="publisher-btn-label">Brouillon</span>
            </button>
          </div>
        </div>
        <div class="publisher-progress" data-progress>
          <div class="publisher-progress-track" data-progress-track></div>
          <div class="publisher-progress-label" data-progress-label></div>
        </div>
      </header>

      <main class="publisher-main" data-main>
        <!-- Contenu dynamique par étape -->
        <div class="publisher-step-content" data-step-content></div>
      </main>

      <footer class="publisher-footer" data-footer>
        <div class="publisher-footer-left">
          <button type="button" class="publisher-btn publisher-btn-ghost" data-action="prev-step" disabled>Précédent</button>
        </div>
        <div class="publisher-footer-right">
          <button type="button" class="publisher-btn publisher-btn-primary" data-action="next-step" disabled>Suivant</button>
        </div>
      </footer>

      <!-- Modales -->
      <div class="publisher-modals" data-modals></div>
    `;
  }

  _config() {
    return FORMAT_CONFIG[this.format] || FORMAT_CONFIG.post;
  }

  _isStepCompleted(stepId) {
    const steps = this._config().steps;
    const currentIdx = steps.indexOf(this.currentStep);
    const stepIdx = steps.indexOf(stepId);
    return stepIdx >= 0 && currentIdx >= 0 && stepIdx < currentIdx;
  }

  _renderStep() {
    if (this._renderedStep === this.currentStep) {
      return;
    }
    this._renderedStep = this.currentStep;
    const content = this.element.querySelector('[data-step-content]');
    content.innerHTML = this._getStepContent(this.currentStep);
    this._bindStepEvents(this.currentStep);
  }

  _getStepContent(step) {
    switch (step) {
      case 'media':
        return '<div class="publisher-media-host" data-media-host></div>';
      case 'adjust':
        return '<div class="publisher-adjust-host" data-adjust-host></div>';
      case 'compose':
        return '<div class="publisher-compose-host" data-compose-host></div>';
      case 'music':
        return '<div class="publisher-music-host" data-music-host></div>';
      case 'caption':
        return '<div class="publisher-caption-host" data-caption-host></div>';
      case 'preview':
        return '<div class="publisher-preview-host" data-preview-host></div>';
      case 'publish':
        return '<div class="publisher-publish-host" data-publish-host></div>';
      default:
        return '<div class="publisher-empty">Étape inconnue</div>';
    }
  }

  _bindStepEvents(step) {
    switch (step) {
      case 'media':
        this._mountMediaPicker();
        break;
      case 'adjust':
        this._mountAdjustEditor();
        break;
      case 'compose':
        this._mountComposeEditor();
        break;
      case 'music':
        this._mountMusicStep();
        break;
      case 'caption':
        this._mountCaptionEditor();
        break;
      case 'preview':
        this._mountPreview();
        break;
      case 'publish':
        this._mountPublish();
        break;
    }
  }

  _mountMediaPicker() {
    const host = this.element.querySelector('[data-media-host]');
    if (!host) {
      console.warn('[Publisher] Media host not found, retrying...');
      setTimeout(() => this._mountMediaPicker(), 50);
      return;
    }
    if (this.mediaPicker) {
      this.mediaPicker.destroy();
      this.mediaPicker = null;
    }
    const config = this._config();
    const canSwitchFormat = !this.entryId && !this.isExistingPublication;
    this.mediaPicker = createPublisherMediaPicker({
      format: this.format,
      multiSelect: true,
      maxSelection: config.maxMedia,
      minSelection: config.minMedia,
      allowedTypes: config.allowedTypes,
      formats: FORMAT_CONFIG,
      canSwitchFormat,
      onFormatChange: (nextFormat) => this._switchFormat(nextFormat),
      onSelectionChange: () => {},
      onComplete: () => publisherStore.nextStep(),
      onCancel: () => this._goBack(),
    });
    // Réinitialiser le flag de restauration à chaque remontée sur l'étape media
    this._mediaRestored = false;
    try {
      this.mediaPicker.mount(host);
    } catch (e) {
      console.error('[Publisher] Media picker mount failed:', e);
    }
  }

  _mountAdjustEditor() {
    const host = this.element.querySelector('[data-adjust-host]');
    // Recadrage / réorganisation des médias (post, carousel, reel, story)
    if (this.adjustEditor) {
      this.adjustEditor.destroy();
      this.adjustEditor = null;
    }
    // Diagnostique : si le draft est vide alors que le picker a une sélection,
    // on restaure les médias depuis le picker avant de monter l'éditeur.
    // Cela couvre le cas où addMedia n'a pas persisté dans le draft.
    if (
      !this._mediaRestored &&
      publisherStore.draft.media.length === 0 &&
      this.mediaPicker?.selectedIds?.size
    ) {
      const media = [];
      for (const id of this.mediaPicker.selectedIds) {
        const photo = this.mediaPicker.photos.find(p => String(p.id) === String(id));
        if (photo) {
          media.push({
            id: String(photo.id),
            url: photo.file_url || `/photos/${photo.id}/file`,
            thumbnail_url: photo.thumbnail_url || `/photos/${photo.id}/file?size=small`,
            type: photo.mime_type?.startsWith('video/') ? 'video' : 'photo',
            source: 'library',
          });
        }
      }
      if (media.length) {
        // Insertion directe dans le draft + un seul _notify pour éviter la boucle
        // avec _subscribeStore du MediaPicker (qui recrée selectedIds depuis draft.media).
        publisherStore.draft.media.push(...media);
        publisherStore.draft.updatedAt = Date.now();
        publisherStore._notify();
        this._mediaRestored = true;
      }
    }
    console.log('[Publisher] adjust step mounted, media count =', publisherStore.draft.media.length);
    this.adjustEditor = createPublisherPostEditor({
      draft: publisherStore.draft,
      format: this.format,
      onSave: () => publisherStore.nextStep(),
      onBack: () => publisherStore.prevStep(),
    });
    this.adjustEditor.mount(host);
  }

  _mountComposeEditor() {
    const host = this.element.querySelector('[data-compose-host]');
    if (this.format === 'story') {
      // StoryEditorView existe déjà
      if (this.formatEditor) {
        this.formatEditor.destroy();
        this.formatEditor = null;
      }
      this.formatEditor = createPublisherStoryEditor({
        draft: publisherStore.draft,
        onSave: () => publisherStore.nextStep(),
        onBack: () => publisherStore.prevStep(),
      });
      this.formatEditor.mount(host);
    } else if (this.format === 'reel') {
      if (this.formatEditor) {
        this.formatEditor.destroy();
        this.formatEditor = null;
      }
      this.formatEditor = createPublisherReelEditor({
        draft: publisherStore.draft,
        onSave: () => publisherStore.nextStep(),
        onBack: () => publisherStore.prevStep(),
      });
      this.formatEditor.mount(host);
    } else {
      // Post/Carrousel ne passent pas par compose ; sécurité
      publisherStore.nextStep();
    }
  }

  _mountMusicStep() {
    const host = this.element.querySelector('[data-music-host]');
    if (!host) return;
    if (this.musicStep) {
      this.musicStep.destroy();
      this.musicStep = null;
    }
    this.musicStep = createPublisherMusicStep();
    this.musicStep.mount(host);
  }

  _mountCaptionEditor() {
    const host = this.element.querySelector('[data-caption-host]');
    if (this.captionEditor) {
      this.captionEditor.destroy();
      this.captionEditor = null;
    }
    this.captionEditor = createPublisherCaptionEditor({
      draft: publisherStore.draft,
      aiAvailable: !!publisherDraftService.currentDraftId,
      onAIRequest: (request) => this._handleAIRequest(request),
    });
    this.captionEditor.mount(host);
  }

  _mountPreview() {
    const host = this.element.querySelector('[data-preview-host]');
    if (this.preview) {
      this.preview.destroy();
      this.preview = null;
    }
    this.preview = createPublisherPreview({
      draft: publisherStore.draft,
      format: this.format,
      onBack: () => publisherStore.prevStep(),
    });
    this.preview.mount(host);
  }

  _storyPublishStatus() {
    const design = publisherStore.draft.design || {};
    const slideCount = (design.slides || []).length;
    if (slideCount === 0) {
      return { canPublish: false, label: 'Aucune slide — revenez à « Composer ».' };
    }
    if (storySlidesReady(design)) {
      return { canPublish: true, label: `${slideCount} slide(s) exportée(s), prête(s).` };
    }
    // Le pipeline final exporte les slides non préparées avant publication.
    return { canPublish: true, label: `${slideCount} slide(s) à exporter à la publication.` };
  }

  _mountPublish() {
    const host = this.element.querySelector('[data-publish-host]');
    const storyStatus = this.format === 'story' ? this._storyPublishStatus() : null;
    const draft = publisherStore.draft;
    const caption = draft.caption || {};
    const shortCaption = (value) => value
      ? `${this._esc(String(value).substring(0, 50))}${String(value).length > 50 ? '…' : ''}`
      : '—';
    host.innerHTML = `
      <div class="publisher-publish">
        <h2>Prêt à publier</h2>
        <div class="publisher-publish-summary">
          ${storyStatus ? `
          <div class="publisher-publish-item">
            <label>Rendu Story</label>
            <span>${this._esc(storyStatus.label)}</span>
          </div>` : ''}
          <div class="publisher-publish-item">
            <label>Compte Instagram</label>
            <span>${this._esc(caption.accountUsername || 'Compte configuré')}</span>
          </div>
          <div class="publisher-publish-item">
            <label>Format</label>
            <span>${this._config().icon} ${this._config().label}</span>
          </div>
          <div class="publisher-publish-item">
            <label>Médias</label>
            <span>${draft.media.length} média${draft.media.length > 1 ? 's' : ''}</span>
          </div>
          <div class="publisher-publish-item">
            <label>Légende</label>
            <span>${shortCaption(caption.title)}</span>
          </div>
          <div class="publisher-publish-item">
            <label>Hashtags</label>
            <span>${shortCaption(caption.hashtags)}</span>
          </div>
          ${draft.garmin.activityId ? `
            <div class="publisher-publish-item">
              <label>Activité Garmin</label>
              <span>#${this._esc(draft.garmin.activityId)}</span>
            </div>
          ` : ''}
        </div>
        <div class="publisher-publish-actions">
          <button type="button" class="publisher-btn publisher-btn-secondary" data-action="back">Annuler</button>
          <button type="button" class="publisher-btn publisher-btn-success" data-action="publish-final" ${storyStatus && !storyStatus.canPublish ? 'disabled' : ''}>Publier maintenant</button>
        </div>
      </div>
    `;
    host.querySelector('[data-action="back"]').addEventListener('click', () => publisherStore.prevStep());
    host.querySelector('[data-action="publish-final"]').addEventListener('click', () => this._publish());
  }

  _bindEvents() {
    // Header
    this.element.querySelector('[data-action="back"]').addEventListener('click', () => this._goBack());
    this.element.querySelector('[data-action="save-draft"]').addEventListener('click', () => this._saveDraft());

    // Sélecteur de format
    const formatBtn = this.element.querySelector('[data-action="select-format"]');
    if (formatBtn) {
      formatBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._toggleFormatMenu();
      });
      this.element.querySelectorAll('[data-format]').forEach(opt => {
        opt.addEventListener('click', () => this._switchFormat(opt.dataset.format));
      });
    }

    // Footer
    this.element.querySelector('[data-action="prev-step"]').addEventListener('click', () => {
      this._navLock(() => publisherStore.prevStep());
    });
    this.element.querySelector('[data-action="next-step"]').addEventListener('click', async () => {
      const stepOrder = this._config().steps;
      const currentIdx = stepOrder.indexOf(this.currentStep);
      if (currentIdx === stepOrder.length - 1) {
        this.element.querySelector('[data-action="publish-final"]')?.click();
        return;
      }
      const nextBtn = this.element.querySelector('[data-action="next-step"]');
      this._navLock(async () => {
        // Sauvegarder le design du Studio avant de quitter l'étape compose
        if (this.currentStep === 'compose' && this.formatEditor?.save) {
          try {
            nextBtn.disabled = true;
            nextBtn.textContent = 'Enregistrement…';
            await this.formatEditor.save();
            nextBtn.textContent = 'Suivant';
            nextBtn.disabled = false;
            this._showToast('Modifications enregistrées');
          } catch (error) {
            nextBtn.textContent = 'Suivant';
            nextBtn.disabled = false;
            this._showError(`Échec de la sauvegarde : ${error.message}`);
            throw error; // bloquer la transition
          }
        }
        publisherStore.nextStep();
      }).catch(() => {
        // Erreur déjà affichée par le bloc ci-dessus, on reste sur l'étape courante
      });
    });

    // Fermer le menu de format si on clique ailleurs
    this.element.addEventListener('click', () => this._toggleFormatMenu(false));
  }

  /**
   * Verrou anti double-transition : un second clic rapproché pendant que
   * l'étape change est ignoré. Si l'étape n'a pas bougé (rien à faire),
   * le verrou est relâché immédiatement. Supporte les fonctions async.
   */
  _navLock(fn) {
    if (this._navLocked) return;
    this._navLocked = true;
    const before = this.currentStep;
    Promise.resolve(fn()).then(() => {
      if (this.currentStep === before) {
        this._navLocked = false;
      } else {
        setTimeout(() => { this._navLocked = false; }, 300);
      }
    }).catch(() => {
      this._navLocked = false;
    });
  }

  _toggleFormatMenu(force) {
    const btn = this.element.querySelector('[data-action="select-format"]');
    const menu = this.element.querySelector('[data-format-menu]');
    if (!btn || !menu) return;
    const open = force !== undefined ? force : menu.hidden;
    menu.hidden = !open;
    btn.setAttribute('aria-expanded', String(open));
  }

  _switchFormat(format) {
    this._toggleFormatMenu(false);
    if (!FORMAT_CONFIG[format] || format === this.format) return;
    if (this.onBack) {
      // Publisher embarqué (ex : calendrier) : changer de format sur place,
      // sans quitter le contexte courant. Le brouillon serveur courant porte le
      // format précédent : le détacher avant de réinitialiser le store local.
      publisherDraftService.clearCurrent?.();
      this._renderedStep = null; // force le remontage avec les nouvelles règles
      publisherStore.setFormat(format);
      this._enforceFormatLimits();
      this._updateFormatSelector();
      return;
    }
    this.router.navigate(`/publisher/${format}`);
  }

  /** Met à jour le libellé et l'état actif du sélecteur de format (header). */
  _updateFormatSelector() {
    if (!this.element) return;
    const root = this.element.querySelector('.publisher-header [data-format-root]');
    if (!root) return;
    const config = FORMAT_CONFIG[this.format] || FORMAT_CONFIG.post;
    const icon = root.querySelector('.publisher-format-icon');
    const label = root.querySelector('.publisher-format-label');
    if (icon) icon.textContent = config.icon;
    if (label) label.textContent = config.label;
    root.querySelectorAll('[data-format]').forEach((opt) => {
      opt.classList.toggle('active', opt.dataset.format === this.format);
    });
  }

  _updateStepIndicator() {
    const config = this._config();
    const track = this.element.querySelector('[data-progress-track]');
    const label = this.element.querySelector('[data-progress-label]');
    if (track) {
      track.innerHTML = config.steps.map(id => {
        const meta = STEP_META[id] || { label: id };
        const state = id === this.currentStep ? 'active' : (this._isStepCompleted(id) ? 'done' : '');
        return `<span class="publisher-progress-seg ${state}" data-seg="${id}" title="${meta.label}"></span>`;
      }).join('');
    }
    if (label) {
      const idx = config.steps.indexOf(this.currentStep);
      const meta = STEP_META[this.currentStep] || { label: '' };
      label.textContent = `${idx + 1}/${config.steps.length} · ${meta.label}`;
    }
  }

  /** Masque le header/le footer selon l'étape (chrome unifié). */
  _updateChrome() {
    if (!this.element) return;
    const noHeader = this.currentStep === 'media';
    const noFooter = this.currentStep === 'media' || this.currentStep === 'publish';
    const immersive = this.currentStep === 'compose';
    this.element.classList.toggle('publisher-page--no-header', noHeader && !immersive);
    this.element.classList.toggle('publisher-page--no-footer', noFooter);
    this.element.classList.toggle('publisher-page--immersive', immersive);
  }

  _updateStepContent() {
    if (!this.element) return;
    this._renderStep();
    this._updateChrome();
    this._updateStepIndicator();
    this._updateFooterButtons();
  }

  _captionLength() {
    const c = publisherStore.draft.caption || {};
    return [c.title, c.content, c.hashtags].filter(Boolean).join('\n\n').length;
  }

  _updateFooterButtons() {
    const config = this._config();
    const stepOrder = config.steps;
    const currentIdx = stepOrder.indexOf(this.currentStep);

    const prevBtn = this.element.querySelector('[data-action="prev-step"]');
    const nextBtn = this.element.querySelector('[data-action="next-step"]');
    if (!prevBtn || !nextBtn) return;

    const atFirst = currentIdx <= 0;
    const atLast = currentIdx === stepOrder.length - 1;
    const mediaCount = (publisherStore.draft.media || []).length;
    const mediaTooFew = this.currentStep === 'adjust' && mediaCount < (config.minMedia || 1);
    const captionOver = this.currentStep === 'caption' && this._captionLength() > CAPTION_MAX_LENGTH;

    prevBtn.disabled = atFirst;
    nextBtn.disabled = atLast || mediaTooFew || captionOver;

    if (atLast) {
      nextBtn.textContent = 'Publier';
      nextBtn.classList.add('publisher-btn-success');
      nextBtn.classList.remove('publisher-btn-primary');
    } else {
      nextBtn.textContent = 'Suivant';
      nextBtn.classList.add('publisher-btn-primary');
      nextBtn.classList.remove('publisher-btn-success');
    }
  }

  async _saveDraft() {
    try {
      const draft = publisherStore.draft;
      if (!publisherDraftService.currentDraftId && publisherDraftService.currentDraftType === 'story') {
        // Brouillon local : une Story standalone n'a pas encore de brouillon serveur (A01 hors périmètre).
        this._showToast('Brouillon sauvegardé localement');
        return;
      }
      // Lot 0 (A01) : sans brouillon serveur, le service crée le brouillon
      // standalone puis persiste le contenu local (conservation en attendant).
      await publisherDraftService.save({
        caption: draft.caption,
        media: draft.media,
        design: draft.design,
        music: draft.music,
      });
      this._showToast('Brouillon sauvegardé');
    } catch (error) {
      this._showError(error.message);
    }
  }

  async _publish() {
    try {
      const btn = this.element.querySelector('[data-action="publish-final"]');
      btn.disabled = true;
      btn.textContent = 'Publication…';

      // Le sélecteur met à jour le store local. Persister les changements avant
      // l'appel de publication, qui travaille sur le brouillon côté serveur.
      const draft = publisherStore.draft;
      if (publisherDraftService.currentDraftType !== 'story') {
        // Lot 0 (A01) : save() crée le brouillon standalone serveur si besoin,
        // puis persiste le contenu (caption/médias/design) avant publication.
        await publisherDraftService.save({
          caption: draft.caption,
          media: draft.media,
          design: draft.design,
          music: draft.music,
        });
      }

      const result = await publisherDraftService.publish({
        platforms: ['instagram'],
      });

      // Le backend met en file le job de publication : le résultat Meta arrive
      // plus tard. Ne pas annoncer une publication terminée trop tôt.
      const queued = result?.status === 'queued'
        || (Array.isArray(result?.jobs) && result.jobs.length > 0);
      this._showToast(queued
        ? 'Publication envoyée · traitement en cours'
        : 'Publié avec succès !');
      publisherStore.clear();
      if (this.onBack) this.onBack();
    } catch (error) {
      this._showError(error.message);
      const btn = this.element.querySelector('[data-action="publish-final"]');
      btn.disabled = false;
      btn.textContent = 'Publier maintenant';
    }
  }

  /**
   * Génération de légende via l'endpoint réel
   * POST /community-manager/studio/draft/{id}/generate-text
   */
  async _handleAIRequest({ tone, length } = {}) {
    if (!publisherDraftService.currentDraftId) {
      throw new Error('Assistance IA disponible après création du brouillon depuis le calendrier.');
    }
    const res = await publisherDraftService.generateText({ tone, length });
    if (res && typeof res === 'object') {
      if (typeof res.title === 'string') publisherStore.updateCaption('title', res.title);
      if (typeof res.content === 'string') publisherStore.updateCaption('content', res.content);
      if (typeof res.hashtags === 'string') publisherStore.updateCaption('hashtags', res.hashtags);
    }
    return res;
  }

  _onGarminSelect(activityId) {
    // Charger les photos de l'activité Garmin
    publisherStore.setGarmin(activityId, {}, []);
    this._showToast('Activité Garmin liée');
  }

  _goBack() {
    if (this.onBack) {
      this.onBack();
    } else {
      this.router.navigate('/community-manager');
    }
  }

  _showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'publisher-toast';
    toast.textContent = message;
    this.element.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  _showError(message) {
    this.error = message;
    const alert = document.createElement('div');
    alert.className = 'publisher-alert';
    alert.innerHTML = `<span>${this._esc(message)}</span><button data-dismiss>✕</button>`;
    this.element.querySelector('[data-main]').prepend(alert);
    alert.querySelector('[data-dismiss]').addEventListener('click', () => alert.remove());
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this._garminListener && this.element) this.element.removeEventListener('pmp:garmin-select', this._garminListener);
    if (this.mediaPicker) this.mediaPicker.destroy();
    if (this.captionEditor) this.captionEditor.destroy();
    if (this.preview) this.preview.destroy();
    if (this.formatEditor) this.formatEditor.destroy();
    if (this.adjustEditor) this.adjustEditor.destroy();
    if (this.musicStep) this.musicStep.destroy();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createCommunityPublisherPage(router, options) {
  return new CommunityPublisherPage(router, options);
}
