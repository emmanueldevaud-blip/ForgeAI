/**
 * PublisherCaptionEditor — Éditeur de légende unifié
 * Titre, contenu, hashtags, compteur, IA intégrée
 */

import { publisherStore } from '../stores/publisherStore.js';

const MAX_LENGTH = 2200;

export class PublisherCaptionEditor {
  constructor(options = {}) {
    this.onSave = options.onSave || (() => {});
    this.onBack = options.onBack || (() => {});
    this.onAIRequest = options.onAIRequest || (() => {});
    this.element = null;
    this.aiPanelOpen = false;
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = 'publisher-caption-editor';
    this.element.innerHTML = this._render();
    host.appendChild(this.element);

    this._bindEvents();
    this._subscribeStore();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      this._updateCounter();
      this._updateAIButton();
    });
  }

  _render() {
    const draft = publisherStore.draft;
    const fullCaption = this._getFullCaption(draft.caption);
    const length = fullCaption.length;
    const overLimit = length > MAX_LENGTH;
    const nearLimit = length > MAX_LENGTH * 0.9;

    return `
      <div class="pce-header">
        <h2>Légende</h2>
        <div class="pce-counter ${overLimit ? 'over' : ''} ${nearLimit && !overLimit ? 'warning' : ''}">
          <span class="pce-current">${length}</span> / <span class="pce-max">${MAX_LENGTH}</span>
          ${overLimit ? '<span class="pce-error">Limite dépassée</span>' : nearLimit ? '<span class="pce-warning">Proche de la limite</span>' : ''}
        </div>
      </div>

      <form class="pce-form" data-form>
        <div class="pce-field">
          <label for="pce-title">Titre (accroche)</label>
          <input type="text" id="pce-title" name="title" maxlength="125" placeholder="Votre accroche…" value="${this._esc(draft.caption.title)}">
          <span class="pce-hint">Première ligne de la publication (max 125 caractères)</span>
        </div>

        <div class="pce-field">
          <label for="pce-content">Contenu</label>
          <textarea id="pce-content" name="content" rows="4" placeholder="Racontez votre histoire…">${this._esc(draft.caption.content)}</textarea>
        </div>

        <div class="pce-field">
          <label for="pce-hashtags">Hashtags</label>
          <textarea id="pce-hashtags" name="hashtags" rows="2" placeholder="#trailrunning #montagne…">${this._esc(draft.caption.hashtags)}</textarea>
          <span class="pce-hint">Séparez par des espaces</span>
        </div>

        <div class="pce-field">
          <label>Compte cible</label>
          <div class="pce-account-selector" data-account-selector>
            <button type="button" class="pce-account-btn" data-action="select-account">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
              </svg>
              <span>Choisir un compte Instagram</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>
        </div>
      </form>

      <div class="pce-ai-panel" data-ai-panel hidden>
        <div class="pce-ai-header">
          <h3>Assistance IA</h3>
          <button type="button" class="pce-btn pce-btn-ghost" data-action="close-ai">✕</button>
        </div>
        <div class="pce-ai-actions">
          <button type="button" class="pce-ai-btn" data-ai-action="generate">✨ Générer une légende</button>
          <button type="button" class="pce-ai-btn" data-ai-action="reformulate">🔄 Reformuler</button>
          <button type="button" class="pce-ai-btn" data-ai-action="hashtags"># Hashtags</button>
          <button type="button" class="pce-ai-btn" data-ai-action="hook">🎯 Accroche</button>
        </div>
        <div class="pce-ai-options">
          <label>Ton
            <select name="tone">
              <option value="humour">Humour & autodérision</option>
              <option value="performance">Performance</option>
              <option value="aventure">Aventure & émotion</option>
              <option value="statistique">Statistique</option>
            </select>
          </label>
          <label>Format
            <select name="format">
              <option value="post">Publication</option>
              <option value="reel">Reel</option>
              <option value="story">Story</option>
            </select>
          </label>
        </div>
        <div class="pce-ai-result" data-ai-result hidden></div>
      </div>

      <div class="pce-actions">
        <button type="button" class="pce-btn pce-btn-secondary" data-action="back">Retour</button>
        <button type="button" class="pce-btn pce-btn-primary" data-action="ai-toggle" aria-expanded="false">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/>
            <line x1="12" y1="22" x2="12" y2="15.5"/>
          </svg>
          IA
        </button>
        <button type="button" class="pce-btn pce-btn-success" data-action="save">Suivant</button>
      </div>
    `;
  }

  _bindEvents() {
    // Formulaire - sync en temps réel
    const form = this.element.querySelector('[data-form]');
    form.addEventListener('input', (e) => {
      const { name, value } = e.target;
      if (name in publisherStore.draft.caption) {
        publisherStore.updateCaption(name, value);
      }
    });

    // Compteur en temps réel
    const titleInput = form.elements.title;
    const contentInput = form.elements.content;
    const hashtagsInput = form.elements.hashtags;
    [titleInput, contentInput, hashtagsInput].forEach(input => {
      input.addEventListener('input', () => this._updateCounter());
    });

    // Actions
    this.element.querySelector('[data-action="back"]').addEventListener('click', () => this.onBack());
    this.element.querySelector('[data-action="save"]').addEventListener('click', () => this.onSave());

    // IA Panel
    this.element.querySelector('[data-action="ai-toggle"]').addEventListener('click', () => this._toggleAIPanel());
    this.element.querySelector('[data-action="close-ai"]').addEventListener('click', () => this._toggleAIPanel(false));

    // IA Actions
    this.element.querySelectorAll('[data-ai-action]').forEach(btn => {
      btn.addEventListener('click', () => this._handleAIAction(btn.dataset.aiAction));
    });

    // Account selector
    this.element.querySelector('[data-action="select-account"]').addEventListener('click', () => this._openAccountSelector());
  }

  _getFullCaption(caption) {
    return [caption.title, caption.content, caption.hashtags].filter(Boolean).join('\n\n');
  }

  _updateCounter() {
    const draft = publisherStore.draft;
    const fullCaption = this._getFullCaption(draft.caption);
    const length = fullCaption.length;
    const overLimit = length > MAX_LENGTH;
    const nearLimit = length > MAX_LENGTH * 0.9 && !overLimit;

    const current = this.element.querySelector('.pce-current');
    const counter = this.element.querySelector('.pce-counter');
    const saveBtn = this.element.querySelector('[data-action="save"]');

    if (current) current.textContent = length;
    if (counter) {
      counter.classList.toggle('over', overLimit);
      counter.classList.toggle('warning', nearLimit);
    }
    if (saveBtn) saveBtn.disabled = overLimit;
  }

  _updateAIButton() {
    const btn = this.element.querySelector('[data-action="ai-toggle"]');
    if (btn) {
      btn.setAttribute('aria-expanded', this.aiPanelOpen);
    }
  }

  _toggleAIPanel(open) {
    this.aiPanelOpen = open !== undefined ? open : !this.aiPanelOpen;
    const panel = this.element.querySelector('[data-ai-panel]');
    const btn = this.element.querySelector('[data-action="ai-toggle"]');
    if (panel) panel.hidden = !this.aiPanelOpen;
    if (btn) btn.setAttribute('aria-expanded', this.aiPanelOpen);
  }

  _handleAIAction(action) {
    const tone = this.element.querySelector('[name="tone"]').value;
    const format = this.element.querySelector('[name="format"]').value;
    const currentCaption = this._getFullCaption(publisherStore.draft.caption);

    this.onAIRequest({ action, tone, format, currentCaption });
    this._showAIResult(`Génération ${action} en cours…`);
  }

  _showAIResult(text) {
    const result = this.element.querySelector('[data-ai-result]');
    result.hidden = false;
    result.textContent = text;
  }

  _openAccountSelector() {
    // TODO: Ouvrir le sélecteur de comptes Meta
    alert('Sélecteur de comptes Meta - à connecter avec l\'API existante');
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&', '<': '<', '>': '>', '"': '"', "'": "'" }[c]));
  }
}

export function createPublisherCaptionEditor(options) {
  return new PublisherCaptionEditor(options);
}