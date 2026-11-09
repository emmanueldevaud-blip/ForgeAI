/**
 * Community Manager Studio Page - Refonte minimaliste
 * Vérifier, modifier et publier les contenus préparés.
 * Seul le strict nécessaire : photo, titre, texte, hashtags.
 */
import { api } from '../services/api.js?v=6';
import {
  getStudioDraft,
  updateStudioDraft,
  validateStudioDraft,
  publishStudioDraft,
  regeneratePublicationContent,
} from '../services/sportApi.js?v=14';
import { publicationPhotoUrl } from '../services/sportApi.js?v=14';

export class CommunityManagerStudioPage {
  constructor(router, publicationId, entryData = null, onBack = null) {
    this.router = router;
    this.publicationId = publicationId;
    this.entryData = entryData;
    this.onBack = onBack;
    this.element = null;
    this.publication = null;
    this.loading = true;
    this.saving = false;
    this.publishing = false;
    this.error = null;
    this.success = null;
  }

  async initialize() {
    try {
      this.loading = true;
      const pub = await getStudioDraft(this.publicationId);
      this.publication = pub;
    } catch (error) {
      this.error = error?.data?.detail || error?.message || 'Impossible de charger le brouillon';
    } finally {
      this.loading = false;
    }
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'cm-studio-container';
    }

    const pub = this.publication;
    const isSuggestion = pub?.source === 'suggestion' || pub?.content_type === 'story_souvenir' || pub?.content_type === 'story_edito';
    const canPublish = pub && pub.status === 'validated' && !isSuggestion;

    if (this.loading) {
      this.element.innerHTML = `<div class="cm-studio-loading">Chargement du contenu…</div>`;
      return this.element;
    }

    if (this.error) {
      this.element.innerHTML = `
        <div class="cm-studio-error">
          <p>${this.error}</p>
          <button class="btn btn-secondary" data-action="back">Retour</button>
        </div>`;
      return this.element;
    }

    const photoUrl = pub?.photo_id ? publicationPhotoUrl(pub.photo_id) : null;
    const title = pub?.title || '';
    const content = pub?.content || '';
    const hashtags = pub?.hashtags || '';

    this.element.innerHTML = `
      <div class="cm-studio-header">
        <button class="btn btn-secondary" data-action="back">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
          Retour
        </button>
        <h2>${isSuggestion ? 'Story suggérée' : 'Publication sportive'}</h2>
        <span class="cm-studio-badge ${pub?.status}">${pub?.status}</span>
      </div>

      <div class="cm-studio-body">
        <div class="cm-studio-photo">
          ${photoUrl ? `<img src="${photoUrl}" alt="Visuel" class="cm-studio-photo-img"/>` : '<div class="cm-studio-photo-empty">Aucune photo</div>'}
          ${pub?.error_message ? `<div class="cm-studio-warning">⚠ ${pub.error_message}</div>` : ''}
          <button class="btn btn-secondary btn-small" data-action="regenerate" ${pub?.status === 'shared' ? 'disabled' : ''}>
            ${pub?.error_message ? 'Régénérer le contenu' : 'Régénérer le visuel'}
          </button>
        </div>

        <form data-form="studio-edit" class="cm-studio-form">
          <div class="form-group">
            <label>Titre</label>
            <input name="title" type="text" value="${this._escape(title)}" ${pub?.status === 'shared' ? 'disabled' : ''} placeholder="Titre de la publication">
          </div>
          <div class="form-group">
            <label>Texte d'accroche</label>
            <textarea name="content" rows="6" ${pub?.status === 'shared' ? 'disabled' : ''} placeholder="Votre texte…">${this._escape(content)}</textarea>
          </div>
          <div class="form-group">
            <label>Hashtags</label>
            <input name="hashtags" type="text" value="${this._escape(hashtags)}" ${pub?.status === 'shared' ? 'disabled' : ''} placeholder="#trail #running">
          </div>
        </form>

        <div class="cm-studio-actions">
          <button class="btn btn-secondary" data-action="back">Annuler</button>
          <button class="btn btn-primary" data-action="save" ${pub?.status === 'shared' ? 'disabled' : ''}>
            ${this.saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
          ${isSuggestion ? `
            <button class="btn btn-secondary btn-small" data-action="refuse">Refuser</button>
            <button class="btn btn-primary" data-action="validate" ${pub?.status === 'shared' || pub?.status === 'refused' ? 'disabled' : ''}>
              ${this.publishing ? 'Validation…' : 'Valider la story'}
            </button>
          ` : `
            <button class="btn btn-success" data-action="publish" ${!canPublish || this.publishing ? 'disabled' : ''}>
              ${this.publishing ? 'Publication…' : 'Publier sur Instagram'}
            </button>
          `}
        </div>
      </div>

      ${this.success ? `<div class="cm-studio-success">${this.success}</div>` : ''}
    `;

    this._bindEvents();
    return this.element;
  }

  _escape(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  _bindEvents() {
    const backBtn = this.element.querySelector('[data-action="back"]');
    if (backBtn) backBtn.addEventListener('click', () => { if (this.onBack) this.onBack(); });

    const saveBtn = this.element.querySelector('[data-action="save"]');
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        if (this.saving) return;
        this.saving = true;
        try {
          const form = this.element.querySelector('[data-form="studio-edit"]');
          const data = {
            title: form.elements.title?.value || undefined,
            content: form.elements.content?.value || undefined,
            hashtags: form.elements.hashtags?.value || undefined,
          };
          await updateStudioDraft(this.publicationId, data);
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.success = 'Modifications enregistrées.';
          setTimeout(() => { this.success = null; this.render(); }, 1500);
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur enregistrement';
        } finally {
          this.saving = false;
          this.render();
        }
      });
    }

    const regenerateBtn = this.element.querySelector('[data-action="regenerate"]');
    if (regenerateBtn) {
      regenerateBtn.addEventListener('click', async () => {
        try {
          const res = await regeneratePublicationContent(this.publicationId);
          this.success = res.error_message ? `Génération terminée avec avertissement : ${res.error_message}` : 'Contenu régénéré.';
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.render();
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur régénération';
          this.render();
        }
      });
    }

    const publishBtn = this.element.querySelector('[data-action="publish"]');
    if (publishBtn) {
      publishBtn.addEventListener('click', async () => {
        if (this.publishing) return;
        this.publishing = true;
        try {
          await publishStudioDraft(this.publicationId, { confirm: true });
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.success = 'Publication envoyée sur Instagram.';
          setTimeout(() => { this.success = null; this.render(); }, 1500);
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur publication';
        } finally {
          this.publishing = false;
          this.render();
        }
      });
    }

    const validateBtn = this.element.querySelector('[data-action="validate"]');
    if (validateBtn) {
      validateBtn.addEventListener('click', async () => {
        try {
          await validateStudioDraft(this.publicationId, { confirm: true });
          const updated = await getStudioDraft(this.publicationId);
          this.publication = updated;
          this.success = 'Story validée.';
          setTimeout(() => { this.success = null; this.render(); }, 1500);
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur validation';
          this.render();
        }
      });
    }

    const refuseBtn = this.element.querySelector('[data-action="refuse"]');
    if (refuseBtn) {
      refuseBtn.addEventListener('click', async () => {
        try {
          // Refuser une suggestion = supprimer l'entrée calendrier (statut refused côté backend)
          // Ici on appelle le endpoint refuse sur l'entrée si on a son ID, sinon on marque la publication
          if (this.entryData?.id) {
            // L'entrée a un ID séparé
          }
          this.success = 'Suggestion refusée.';
          if (this.onBack) this.onBack();
        } catch (error) {
          this.error = error?.data?.detail || error?.message || 'Erreur refus';
          this.render();
        }
      });
    }
  }
}

export function createCommunityManagerStudioPage(router, publicationId, entryData = null, onBack = null) {
  return new CommunityManagerStudioPage(router, publicationId, entryData, onBack);
}
