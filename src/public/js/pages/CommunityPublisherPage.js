/**
 * CommunityPublisherPage — Point d'entrée unique pour la création
 * Publication, Reel, Story — Interface unifiée style Instagram
 */

import { publisherStore } from '../stores/publisherStore.js';
import { publisherDraftService } from '../services/publisherDraftService.js';
import { createPublisherMediaPicker } from '../components/PublisherMediaPicker.js';
import { createPublisherCaptionEditor } from '../components/PublisherCaptionEditor.js';
import { createPublisherPreview } from '../components/PublisherPreview.js';
import { createPublisherPostEditor } from '../editors/PublisherPostEditor.js';
import { createPublisherReelEditor } from '../editors/PublisherReelEditor.js';
import { createPublisherStoryEditor } from '../editors/PublisherStoryEditor.js';

const STEPS = [
  { id: 'media', label: 'Médias', icon: '📷' },
  { id: 'adjust', label: 'Ajuster', icon: '✂️' },
  { id: 'compose', label: 'Composer', icon: '✨' },
  { id: 'caption', label: 'Légende', icon: '📝' },
  { id: 'preview', label: 'Aperçu', icon: '👁️' },
  { id: 'publish', label: 'Publier', icon: '🚀' },
];

const FORMAT_CONFIG = {
  post: { label: 'Publication', icon: '📸', steps: ['media', 'adjust', 'caption', 'preview', 'publish'], maxMedia: 10 },
  reel: { label: 'Reel', icon: '🎬', steps: ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'], maxMedia: 20 },
  story: { label: 'Story', icon: '📖', steps: ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'], maxMedia: 10 },
};

export class CommunityPublisherPage {
  constructor(router, options = {}) {
    this.router = router;
    this.entryId = options.entryId || null;
    this.format = options.format || 'post';
    this.garminActivityId = options.garminActivityId || null;
    this.preselectedMedia = options.preselectedMedia || [];
    this.onBack = options.onBack || null;
    this.isExistingPublication = options.isExistingPublication || false;

    this.element = null;
    this.mediaPicker = null;
    this.captionEditor = null;
    this.preview = null;
    this.formatEditor = null; // Post/Reel/Story editor
    this.adjustEditor = null; // PublisherPostEditor (recadrage / réorganisation)
    this.currentStep = 'media';
    this.loading = false;
    this.error = null;
    this._renderedStep = null;
    this._unsubscribeStore = null;
    this._garminListener = null;
  }

  async initialize() {
    // Charger le brouillon existant ou en créer un nouveau
    if (this.isExistingPublication) {
      await this._loadExistingPublication(this.entryId);
    } else if (this.entryId) {
      await this._loadFromCalendarEntry();
    } else if (this.garminActivityId) {
      await this._loadFromGarmin();
    } else {
      publisherStore.resetDraft(this.format);
    }

    // Appliquer les médias pré-sélectionnés
    if (this.preselectedMedia.length) {
      publisherStore.draft.media = this.preselectedMedia.map((m, i) => ({
        ...m,
        id: m.id || `media_${Date.now()}_${i}`,
        order: i,
      }));
      publisherStore._notify();
    }
  }

  async _loadFromCalendarEntry() {
    try {
      const res = await publisherDraftService.createFromCalendar({
        calendarEntryId: this.entryId,
        format: this.format,
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
  }

  async _loadExistingPublication(publicationId) {
    try {
      const pub = await publisherDraftService.load(publicationId);
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
      this._subscribeStore();
      this._renderStep();
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
    this._unsubscribeStore = publisherStore.subscribe(state => {
      this.format = state.draft.format;
      this.currentStep = state.ui.currentStep;
      this._updateStepIndicator();
      this._updateStepContent();
    });
  }

  _renderShell() {
    const config = FORMAT_CONFIG[this.format];
    return `
      <header class="publisher-header">
        <div class="publisher-header-left">
          <button type="button" class="publisher-btn publisher-btn-back" data-action="back">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
            </svg>
          </button>
          <h1>${config.icon} ${config.label}</h1>
        </div>
        <div class="publisher-header-center">
          <div class="publisher-steps" data-steps>
            ${STEPS.map(s => `
              <button type="button" class="publisher-step ${this.currentStep === s.id ? 'active' : ''} ${this._isStepCompleted(s.id) ? 'completed' : ''}" data-step="${s.id}" ${!config.steps.includes(s.id) ? 'disabled' : ''}>
                <span class="publisher-step-icon">${s.icon}</span>
                <span class="publisher-step-label">${s.label}</span>
              </button>
            `).join('')}
          </div>
        </div>
        <div class="publisher-header-right">
          <button type="button" class="publisher-btn publisher-btn-secondary" data-action="save-draft">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/></svg>
            Brouillon
          </button>
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

  _isStepCompleted(stepId) {
    const order = ['media', 'adjust', 'compose', 'caption', 'preview', 'publish'];
    const currentIdx = order.indexOf(this.currentStep);
    const stepIdx = order.indexOf(stepId);
    return stepIdx < currentIdx;
  }

  _renderStep() {
    if (this._renderedStep === this.currentStep) {
      return;
    }
    this._renderedStep = this.currentStep;
    const content = this.element.querySelector('[data-step-content]');
    content.innerHTML = this._getStepContent(this.currentStep);
    const footer = this.element.querySelector('[data-footer]');
    if (footer) footer.style.display = this.currentStep === 'media' ? 'none' : '';
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
    this.mediaPicker = createPublisherMediaPicker({
      multiSelect: true,
      maxSelection: FORMAT_CONFIG[this.format].maxMedia,
      allowedTypes: this.format === 'reel' ? ['photo', 'video'] : ['photo'],
      onSelectionChange: () => {},
      onComplete: () => publisherStore.nextStep(),
      onCancel: () => this._goBack(),
    });
    try {
      this.mediaPicker.mount(host);
    } catch (e) {
      console.error('[Publisher] Media picker mount failed:', e);
    }
  }

  _mountAdjustEditor() {
    const host = this.element.querySelector('[data-adjust-host]');
    // Pour post/reel: recadrage, réorganisation
    // Pour story: cadrage par slide
    if (this.format === 'story') {
      host.innerHTML = '<div class="publisher-adjust-story">Ajustement des slides Story (à implémenter)</div>';
    } else {
      if (this.adjustEditor) {
        this.adjustEditor.destroy();
        this.adjustEditor = null;
      }
      this.adjustEditor = createPublisherPostEditor({
        draft: publisherStore.draft,
        onSave: () => publisherStore.nextStep(),
        onBack: () => publisherStore.prevStep(),
      });
      this.adjustEditor.mount(host);
    }
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
      // Post simple : pas d'étape compose, on passe directement à caption
      publisherStore.nextStep();
    }
  }

  _mountCaptionEditor() {
    const host = this.element.querySelector('[data-caption-host]');
    if (this.captionEditor) {
      this.captionEditor.destroy();
      this.captionEditor = null;
    }
    this.captionEditor = createPublisherCaptionEditor({
      draft: publisherStore.draft,
      onSave: () => publisherStore.nextStep(),
      onBack: () => publisherStore.prevStep(),
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
      onPublish: () => publisherStore.setStep('publish'),
    });
    this.preview.mount(host);
  }

  _mountPublish() {
    const host = this.element.querySelector('[data-publish-host]');
    host.innerHTML = `
      <div class="publisher-publish">
        <h2>Prêt à publier</h2>
        <div class="publisher-publish-summary">
          <div class="publisher-publish-item">
            <label>Format</label>
            <span>${FORMAT_CONFIG[this.format].icon} ${FORMAT_CONFIG[this.format].label}</span>
          </div>
          <div class="publisher-publish-item">
            <label>Médias</label>
            <span>${publisherStore.draft.media.length} média${publisherStore.draft.media.length > 1 ? 's' : ''}</span>
          </div>
          <div class="publisher-publish-item">
            <label>Légende</label>
            <span>${publisherStore.draft.caption.title ? publisherStore.draft.caption.title.substring(0, 50) + '…' : '—'}</span>
          </div>
          <div class="publisher-publish-item">
            <label>Hashtags</label>
            <span>${publisherStore.draft.caption.hashtags ? publisherStore.draft.caption.hashtags.substring(0, 50) + '…' : '—'}</span>
          </div>
          ${publisherStore.draft.garmin.activityId ? `
            <div class="publisher-publish-item">
              <label>Activité Garmin</label>
              <span>#{publisherStore.draft.garmin.activityId}</span>
            </div>
          ` : ''}
        </div>
        <div class="publisher-publish-actions">
          <button type="button" class="publisher-btn publisher-btn-secondary" data-action="back">Annuler</button>
          <button type="button" class="publisher-btn publisher-btn-success" data-action="publish-final">Publier maintenant</button>
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

    // Steps navigation
    this.element.querySelectorAll('[data-step]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (!btn.disabled) publisherStore.setStep(btn.dataset.step);
      });
    });

    // Footer
    this.element.querySelector('[data-action="prev-step"]').addEventListener('click', () => publisherStore.prevStep());
    this.element.querySelector('[data-action="next-step"]').addEventListener('click', () => {
      const stepOrder = FORMAT_CONFIG[this.format].steps;
      const currentIdx = stepOrder.indexOf(this.currentStep);
      if (currentIdx === stepOrder.length - 1) {
        this.element.querySelector('[data-action="publish-final"]')?.click();
        return;
      }
      publisherStore.nextStep();
    });

    // Publish final
    this.element.querySelector('[data-action="publish-final"]')?.addEventListener('click', () => this._publish());
  }

  _updateStepIndicator() {
    this.element.querySelectorAll('[data-step]').forEach(btn => {
      const step = btn.dataset.step;
      btn.classList.toggle('active', step === this.currentStep);
      btn.classList.toggle('completed', this._isStepCompleted(step));
    });
  }

  _updateStepContent() {
    this._renderStep();
    this._updateFooterButtons();
  }

  _updateFooterButtons() {
    const config = FORMAT_CONFIG[this.format];
    const stepOrder = config.steps;
    const currentIdx = stepOrder.indexOf(this.currentStep);

    const prevBtn = this.element.querySelector('[data-action="prev-step"]');
    const nextBtn = this.element.querySelector('[data-action="next-step"]');

    prevBtn.disabled = currentIdx === 0;
    nextBtn.disabled = currentIdx === stepOrder.length - 1;

    if (currentIdx === stepOrder.length - 1) {
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

      await publisherDraftService.publish({
        platforms: ['instagram'], // TODO: sélecteur de plateforme
      });

      this._showToast('Publié avec succès !');
      publisherStore.clear();
      if (this.onBack) this.onBack();
    } catch (error) {
      this._showError(error.message);
      const btn = this.element.querySelector('[data-action="publish-final"]');
      btn.disabled = false;
      btn.textContent = 'Publier maintenant';
    }
  }

  _handleAIRequest(request) {
    // TODO: Intégrer les appels IA via publisherDraftService
    console.log('[Publisher] AI Request:', request);
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
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&', '<': '<', '>': '>', '"': '"', "'": "'" }[c]));
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this._garminListener) this.element.removeEventListener('pmp:garmin-select', this._garminListener);
    if (this.mediaPicker) this.mediaPicker.destroy();
    if (this.captionEditor) this.captionEditor.destroy();
    if (this.preview) this.preview.destroy();
    if (this.formatEditor) this.formatEditor.destroy();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }
}

export function createCommunityPublisherPage(router, options) {
  return new CommunityPublisherPage(router, options);
}