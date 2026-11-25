/**
 * Story Studio Page — Point d'entrée pour l'éditeur Story Studio.
 * S'ouvre depuis le calendrier éditorial sur un StoryDraft.
 */

import { createStoryEditorView } from '../editor/StoryEditorView.js?v=3';
import { uploadPhotos, photoFileUrl } from '../services/photosApi.js';
import {
  getStoryDraft,
  updateStoryDraft,
  updateStorySlideDesign,
  renderStorySlide,
  getStoryRenderJobs,
  validateStoryDraft,
  publishStoryDraft,
  deleteStoryDraft,
  previewStoryDraft,
  listStoryDrafts,
} from '../services/sportApi.js?v=16';

export class StoryStudioPage {
  constructor(router, draftId, onBack = null) {
    this.router = router;
    this.draftId = draftId;
    this.onBack = onBack;
    this.element = null;
    this.draft = null;
    this.loading = true;
    this.error = null;
    this.editorOpen = false;
    this.editorView = null;
    this.previewOpen = false;
  }

  async initialize() {
    try {
      this.loading = true;
      this.draft = await getStoryDraft(this.draftId);
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Impossible de charger le brouillon Story';
    } finally {
      this.loading = false;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'story-studio-page';
    }

    if (this.editorOpen && this.editorView) {
      return this.element;
    }

    if (this.loading) {
      this.element.innerHTML = `<div class="story-studio-loading">Chargement du Story Studio…</div>`;
      return this.element;
    }

    if (this.error) {
      this.element.innerHTML = `
        <div class="story-studio-error">
          <p>${this._escape(this.error)}</p>
          <button class="btn btn-secondary" data-action="back">Retour</button>
        </div>`;
      this._bindBack();
      return this.element;
    }

    const draft = this.draft;
    const slideCount = draft.design_documents?.length || 0;
    const status = draft.status || 'draft';
    const statusLabels = {
      draft: 'Brouillon',
      preparing: 'Préparation…',
      ready: 'Prêt à éditer',
      editing: 'Édition en cours',
      rendering: 'Rendu…',
      awaiting_validation: 'En attente de validation',
      publishing: 'Publication…',
      published: 'Publié',
      failed: 'Échec',
      cancelled: 'Annulé',
    };

    this.element.innerHTML = `
      <header class="story-studio-header">
        <div class="story-studio-header-left">
          <button type="button" class="btn btn-secondary" data-action="back">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
            </svg>
            Retour
          </button>
          <h1>Story Studio</h1>
        </div>
        <div class="story-studio-header-right">
          <span class="story-status-badge story-status-${status}">${statusLabels[status] || status}</span>
          ${status !== 'published' && status !== 'failed' ? `
            <button type="button" class="btn btn-primary" data-action="open-editor" ${status === 'preparing' ? 'disabled' : ''}>
              ${this.editorOpen ? 'Continuer l\'édition' : 'Ouvrir l\'éditeur'}
            </button>
          ` : ''}
        </div>
      </header>

      <div class="story-studio-overview">
        <div class="story-studio-info">
          <div class="story-info-item">
            <label>Slides</label>
            <span>${slideCount}</span>
          </div>
          <div class="story-info-item">
            <label>Statut</label>
            <span>${statusLabels[status] || status}</span>
          </div>
          <div class="story-info-item">
            <label>Source</label>
            <span>${draft.source === 'garmin' ? 'Activité Garmin' : draft.source === 'calendar' ? 'Calendrier' : 'Manuel'}</span>
          </div>
          ${draft.source_activity_id ? `
            <div class="story-info-item">
              <label>Activité</label>
              <span>#${draft.source_activity_id}</span>
            </div>
          ` : ''}
          ${draft.prepared_at ? `
            <div class="story-info-item">
              <label>Préparé le</label>
              <span>${new Date(draft.prepared_at).toLocaleString('fr-FR')}</span>
            </div>
          ` : ''}
        </div>

        ${draft.caption ? `
          <div class="story-caption-preview">
            <label>Légende</label>
            <p>${this._escape(draft.caption)}</p>
          </div>
        ` : ''}

        ${draft.hashtags ? `
          <div class="story-hashtags-preview">
            <label>Hashtags</label>
            <p>${this._escape(draft.hashtags)}</p>
          </div>
        ` : ''}

        <div class="story-slides-preview">
          <h3>Aperçu des slides (${slideCount})</h3>
          <div class="story-slides-grid">
            ${(draft.design_documents || []).map((design, i) => {
              const slide = draft.slides?.[i] || {};
              return `
                <div class="story-slide-preview-card" data-slide="${i}">
                  <div class="story-slide-preview-thumb">
                    <canvas class="story-slide-canvas" width="160" height="284"></canvas>
                  </div>
                  <div class="story-slide-preview-info">
                    <span class="story-slide-type">${this._getSlideTypeIcon(slide.type)} ${this._escape(slide.type || 'photo')}</span>
                    <span class="story-slide-num">Slide ${i + 1}</span>
                    ${slide.hook ? `<p class="story-slide-hook">${this._escape(slide.hook)}</p>` : ''}
                  </div>
                  <div class="story-slide-preview-actions">
                    <button type="button" class="btn btn-sm btn-secondary" data-action="edit-slide" data-slide="${i}">Éditer</button>
                    ${design.timeline?.tracks?.some(t => t.type === 'video') ? `
                      <button type="button" class="btn btn-sm btn-primary" data-action="render-slide" data-slide="${i}">Rendre</button>
                    ` : ''}
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>

        <div class="story-studio-actions">
          ${status === 'ready' || status === 'editing' ? `
            <button type="button" class="btn btn-primary" data-action="validate" ${slideCount === 0 ? 'disabled' : ''}>
              ✓ Ouvrir l'éditeur pour valider
            </button>
          ` : ''}
          ${status === 'awaiting_validation' ? `
            <button type="button" class="btn btn-success" data-action="publish">
              🚀 Publier les Stories
            </button>
          ` : ''}
          ${status === 'draft' || status === 'ready' || status === 'editing' ? `
            <button type="button" class="btn btn-danger" data-action="delete">
              🗑 Supprimer le brouillon
            </button>
          ` : ''}
        </div>

        ${this.previewOpen ? `
          <div class="story-preview-overlay" data-action="close-preview">
            <div class="story-preview-modal">
              <header class="story-preview-header">
                <h3>Aperçu des ${slideCount} Stories</h3>
                <button type="button" class="btn btn-secondary btn-sm" data-action="close-preview">Fermer</button>
              </header>
              <div class="story-preview-body" data-preview-body></div>
              <footer class="story-preview-footer">
                <button type="button" class="btn btn-secondary" data-action="close-preview">Fermer</button>
                ${status !== 'published' ? `<button type="button" class="btn btn-success" data-action="validate-publish">✓ Valider et publier</button>` : ''}
              </footer>
            </div>
          </div>
        ` : ''}
      </div>
    `;

    this._bindEvents();
    this._renderSlideThumbnails();

    if (this.editorOpen && !this.editorView) {
      this._openEditor();
    }

    return this.element;
  }

  _escape(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&', '<': '<', '>': '>', '"': '"', "'": "'" }[c]));
  }

  _getSlideTypeIcon(type) {
    const icons = {
      intro: '🎬',
      photo: '📷',
      stats: '📊',
      map: '🗺️',
      outro: '🏁',
    };
    return icons[type] || '📄';
  }

  _bindEvents() {
    this.element.querySelectorAll('[data-action="back"]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (this.editorView) this.editorView.destroy();
        if (this.onBack) this.onBack();
      });
    });

    const openEditorBtn = this.element.querySelector('[data-action="open-editor"]');
    if (openEditorBtn) {
      openEditorBtn.addEventListener('click', () => this._openEditor());
    }

    this.element.querySelectorAll('[data-action="edit-slide"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const slideIndex = parseInt(btn.dataset.slide, 10);
        this._openEditor(slideIndex);
      });
    });

    this.element.querySelectorAll('[data-action="render-slide"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const slideIndex = parseInt(btn.dataset.slide, 10);
        btn.disabled = true;
        btn.textContent = 'Rendu…';
        try {
          await renderStorySlide(this.draftId, slideIndex);
          btn.textContent = 'En file';
          setTimeout(() => { btn.disabled = false; btn.textContent = 'Rendre'; this.render(); }, 2000);
        } catch (error) {
          btn.disabled = false;
          btn.textContent = 'Rendre';
          alert(error?.data?.detail || error?.message || 'Erreur de rendu');
        }
      });
    });

    const validateBtn = this.element.querySelector('[data-action="validate"]');
    if (validateBtn) {
      validateBtn.addEventListener('click', () => this._openEditor());
    }

    const publishBtn = this.element.querySelector('[data-action="publish"]');
    if (publishBtn) {
      publishBtn.addEventListener('click', async () => {
        if (!confirm('Publier toutes les Stories sur Instagram ?')) return;
        publishBtn.disabled = true;
        publishBtn.textContent = 'Publication…';
        try {
          const res = await publishStoryDraft(this.draftId, { confirm: true, platforms: ['instagram'] });
          alert(`${res.published_slides} Story(s) en file de publication`);
          this.draft = await getStoryDraft(this.draftId);
          this.render();
        } catch (error) {
          publishBtn.disabled = false;
          publishBtn.textContent = '🚀 Publier les Stories';
          alert(error?.data?.detail || error?.message || 'Erreur de publication');
        }
      });
    }

    const deleteBtn = this.element.querySelector('[data-action="delete"]');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', async () => {
        if (!confirm('Supprimer définitivement ce brouillon Story ?')) return;
        try {
          await deleteStoryDraft(this.draftId);
          if (this.onBack) this.onBack();
        } catch (error) {
          alert(error?.data?.detail || error?.message || 'Erreur de suppression');
        }
      });
    }

    const previewBtn = this.element.querySelector('[data-action="preview-all"]');
    if (previewBtn) {
      previewBtn.addEventListener('click', async () => {
        this.previewOpen = true;
        this.render();
        await this._loadPreview();
      });
    }

    this.element.querySelectorAll('[data-action="close-preview"]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.previewOpen = false;
        this.render();
      });
    });

    const validatePublishBtn = this.element.querySelector('[data-action="validate-publish"]');
    if (validatePublishBtn) {
      validatePublishBtn.addEventListener('click', async () => {
        this.previewOpen = false;
        this.render();
        const validateBtn = this.element.querySelector('[data-action="validate"]');
        if (validateBtn) validateBtn.click();
      });
    }
  }

  async _renderSlideThumbnails() {
    const draft = this.draft;
    for (let i = 0; i < (draft.design_documents?.length || 0); i++) {
      const canvas = this.element.querySelector(`.story-slide-preview-card[data-slide="${i}"] .story-slide-canvas`);
      if (!canvas) continue;
      const design = draft.design_documents[i];
      const ctx = canvas.getContext('2d');
      this._renderSlideThumbnail(ctx, design, 160, 284);
    }
  }

  _renderSlideThumbnail(ctx, design, w, h) {
    // Fond
    ctx.fillStyle = design.background?.color || '#000000';
    ctx.fillRect(0, 0, w, h);

    // Éléments simplifiés
    const elements = design.elements || [];
    for (const el of elements) {
      if (el.type === 'text') {
        ctx.save();
        ctx.font = `${Math.max(10, Math.round((el.size || 24) * w / 1080))}px ${el.font || 'Arial'}`;
        ctx.fillStyle = el.color || '#ffffff';
        ctx.textAlign = el.align || 'center';
        ctx.textBaseline = 'middle';
        const x = (el.x || 0) * w / 1080;
        const y = (el.y || 0) * h / 1920;
        ctx.fillText(el.text || '', x, y);
        ctx.restore();
      } else if (el.type === 'image' && el.src) {
        // Ne pas charger l'image pour la thumbnail
      } else if (el.type === 'sport_stats') {
        ctx.save();
        ctx.font = `bold ${Math.max(8, Math.round((el.size || 24) * w / 1080))}px ${el.font || 'Arial'}`;
        ctx.fillStyle = el.color || '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const x = (el.x || 0) * w / 1080;
        const y = (el.y || 0) * h / 1920;
        const text = `${el.value || ''} ${el.unit || ''}`;
        ctx.fillText(text, x, y);
        ctx.restore();
      }
    }
  }

  async _loadPreview() {
    try {
      const res = await previewStoryDraft(this.draftId);
      const body = this.element.querySelector('[data-preview-body]');
      if (body && res.slides) {
        body.innerHTML = res.slides.map((slide, i) => `
          <div class="story-preview-slide">
            <h4>Slide ${i + 1}: ${this._escape(slide.type || 'photo')}</h4>
            ${slide.hook ? `<p class="story-preview-hook">${this._escape(slide.hook)}</p>` : ''}
            ${slide.caption ? `<p class="story-preview-caption">${this._escape(slide.caption)}</p>` : ''}
          </div>
        `).join('');
      }
    } catch (error) {
      console.error('Erreur aperçu:', error);
    }
  }

  _openEditor(startSlideIndex = 0) {
    if (!this.draft) return;

    const host = document.createElement('div');
    host.className = 'story-studio-editor-host';
    this.element.innerHTML = '';
    this.element.appendChild(host);

    this.editorView = createStoryEditorView({
      draft: this.draft,
      deps: {
        updateDraft: (id, data) => updateStoryDraft(id, data),
        updateSlideDesign: (id, slideIndex, design) => updateStorySlideDesign(id, slideIndex, design),
        renderSlide: (id, slideIndex) => renderStorySlide(id, slideIndex),
        getRenderJobs: (id) => getStoryRenderJobs(id),
        validateDraft: (id) => validateStoryDraft(id),
        publishDraft: (id, data) => publishStoryDraft(id, data),
        previewDraft: (id) => previewStoryDraft(id),
        uploadPhotos,
        photoFileUrl,
      },
      callbacks: {
        onClose: () => this._closeEditor(),
        onSave: async (draftId, data) => {
          this.draft = await getStoryDraft(draftId);
        },
        onPublish: async (draftId, data) => {
          await updateStoryDraft(draftId, data);
          this.draft = await validateStoryDraft(draftId);
          this.editorView?.destroy?.();
          this.editorView = null;
          this.editorOpen = false;
          this.render();
        },
      },
    });

    this.editorView.mount(host);
    this.editorOpen = true;

    // Naviguer vers la slide demandée
    if (startSlideIndex > 0) {
      setTimeout(() => {
        if (this.editorView) this.editorView._switchSlide(startSlideIndex);
      }, 100);
    }
  }

  _closeEditor() {
    if (this.editorView) {
      this.editorView.destroy();
      this.editorView = null;
    }
    this.editorOpen = false;
    this.render();
  }

  destroy() {
    if (this.editorView) {
      this.editorView.destroy();
      this.editorView = null;
    }
    if (this.element && this.element.parentNode) {
      this.element.parentNode.removeChild(this.element);
    }
  }
}

export function createStoryStudioPage(router, draftId, onBack = null) {
  return new StoryStudioPage(router, draftId, onBack);
}
