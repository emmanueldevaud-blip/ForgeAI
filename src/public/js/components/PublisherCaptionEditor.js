/**
 * PublisherCaptionEditor — Éditeur de légende unifié
 * Titre, contenu, hashtags, compteur, IA intégrée
 */

import { publisherStore } from '../stores/publisherStore.js';
import { getMetaInstagramAccount } from '../services/sportApi.js?v=17';

const MAX_LENGTH = 2200;

export class PublisherCaptionEditor {
  constructor(options = {}) {
    this.onAIRequest = options.onAIRequest || (async () => {
      throw new Error('Assistance IA indisponible.');
    });
    this.aiAvailable = options.aiAvailable !== false;
    this.element = null;
    this.aiPanelOpen = false;
    this.instagramAccounts = [];
    this.instagramSelectedIds = [];
    this._accountLoading = false;
    this._aiRunning = false;
    this._unsubscribeStore = null;
  }

  mount(host) {
    this.element = document.createElement('div');
    this.element.className = 'publisher-caption-editor';
    this.element.innerHTML = this._render();
    host.appendChild(this.element);

    this._bindEvents();
    this._subscribeStore();
    this._loadInstagramAccount();
  }

  _subscribeStore() {
    this._unsubscribeStore = publisherStore.subscribe(state => {
      this._updateCounter();
      this._updateAIButton();
      this._syncFieldsFromStore();
    });
  }

  _syncFieldsFromStore() {
    const draft = publisherStore.draft;
    const fields = { title: 'title', content: 'content', hashtags: 'hashtags' };
    for (const [name, key] of Object.entries(fields)) {
      const input = this.element.querySelector(`[name="${name}"]`);
      if (!input || input === document.activeElement) continue;
      const value = draft.caption[key] ?? '';
      if (input.value !== value) input.value = value;
    }
    this._updateCaptionPreview();
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
        <div class="pce-header-actions">
          <div class="pce-counter ${overLimit ? 'over' : ''} ${nearLimit && !overLimit ? 'warning' : ''}">
            <span class="pce-current">${length}</span> / <span class="pce-max">${MAX_LENGTH}</span>
            <span class="pce-error" ${overLimit ? '' : 'hidden'}>Limite dépassée</span>
            <span class="pce-warning" ${nearLimit && !overLimit ? '' : 'hidden'}>Proche de la limite</span>
          </div>
          <button type="button" class="pce-btn pce-btn-secondary" data-action="ai-toggle" aria-expanded="false" aria-controls="pce-ai-panel">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/>
              <line x1="12" y1="22" x2="12" y2="15.5"/>
            </svg>
            IA
          </button>
        </div>
      </div>

      <div class="pce-live-preview" data-caption-preview aria-label="Aperçu Instagram de la légende">
        <div class="pce-live-thumb" data-preview-thumb></div>
        <div class="pce-live-copy">
          <div class="pce-live-account">
            <span class="pce-live-avatar"></span>
            <strong data-preview-account>${this._esc(draft.caption.accountUsername || 'Votre compte')}</strong>
          </div>
          <p class="pce-live-text" data-preview-caption>${this._esc(fullCaption) || 'Votre légende apparaîtra ici…'}</p>
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
          <div class="pce-emoji-picker" aria-label="Ajouter un emoji">
            ${['😀', '😍', '😂', '🥹', '🔥', '❤️', '👏', '🙌', '✨', '🎉', '💪', '🏃', '🌍', '☀️', '⛰️', '📍'].map(emoji => `<button type="button" data-emoji="${emoji}" aria-label="Ajouter ${emoji}">${emoji}</button>`).join('')}
          </div>
        </div>

        <div class="pce-field">
          <label for="pce-hashtags">Hashtags</label>
          <textarea id="pce-hashtags" name="hashtags" rows="2" placeholder="#trailrunning #montagne…">${this._esc(draft.caption.hashtags)}</textarea>
          <div class="pce-hashtag-suggestions" aria-label="Suggestions de hashtags">
            ${['#trailrunning', '#running', '#montagne', '#outdoor'].map(tag => `<button type="button" data-hashtag="${tag}">${tag}</button>`).join('')}
          </div>
          <span class="pce-hint">Touchez un hashtag pour l’ajouter · séparez par des espaces</span>
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
            <div class="pce-account-panel" data-account-panel hidden>
              <div class="pce-account-empty" data-account-empty hidden>Aucun compte Instagram configure.</div>
              <div class="pce-account-list" data-account-list></div>
              <div class="pce-account-footer">
                <button type="button" class="pce-btn pce-btn-secondary" data-action="confirm-account-selection">Confirmer la sélection</button>
              </div>
            </div>
          </div>
        </div>
      </form>

      <div class="pce-ai-panel" id="pce-ai-panel" data-ai-panel hidden>
        <div class="pce-ai-header">
          <h3>Assistance IA</h3>
          <button type="button" class="pce-btn pce-btn-ghost" data-action="close-ai" aria-label="Fermer">✕</button>
        </div>
        <div class="pce-ai-options">
          <label>Ton
            <select name="tone" data-ai-tone ${this.aiAvailable ? '' : 'disabled'}>
              <option value="humour">Humour & autodérision</option>
              <option value="performance">Performance</option>
              <option value="aventure">Aventure & émotion</option>
              <option value="statistique">Statistique</option>
            </select>
          </label>
          <label>Longueur
            <select name="length" data-ai-length ${this.aiAvailable ? '' : 'disabled'}>
              <option value="short">Courte</option>
              <option value="long">Longue</option>
            </select>
          </label>
        </div>
        <div class="pce-ai-actions">
          <button type="button" class="pce-ai-btn" data-ai-action="generate" ${this.aiAvailable ? '' : 'disabled'}>
            ✨ Générer la légende
          </button>
        </div>
        ${this.aiAvailable ? '' : `
          <p class="pce-ai-hint">L'assistance IA s'active après la création du brouillon depuis le calendrier éditorial.</p>
        `}
        <div class="pce-ai-result" data-ai-result hidden></div>
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
    this.element.querySelectorAll('[data-emoji]').forEach((button) => {
      button.addEventListener('click', () => this._insertEmoji(button.dataset.emoji));
    });
    this.element.querySelectorAll('[data-hashtag]').forEach((button) => {
      button.addEventListener('click', () => this._appendHashtag(button.dataset.hashtag));
    });

    // IA Panel
    this.element.querySelector('[data-action="ai-toggle"]').addEventListener('click', () => this._toggleAIPanel());
    this.element.querySelector('[data-action="close-ai"]').addEventListener('click', () => this._toggleAIPanel(false));

    // IA Action
    this.element.querySelectorAll('[data-ai-action]').forEach(btn => {
      btn.addEventListener('click', () => this._handleAIAction(btn.dataset.aiAction));
    });

    // Account selector
    const accountBtn = this.element.querySelector('[data-action="select-account"]');
    accountBtn.addEventListener('click', () => this._openAccountSelector());
    const confirmBtn = this.element.querySelector('[data-action="confirm-account-selection"]');
    if (confirmBtn) confirmBtn.addEventListener('click', () => this._confirmAccountSelection());
    this.element.querySelectorAll('[data-account-id]').forEach(btn => {
      btn.addEventListener('click', () => this._selectAccount(btn.dataset.accountId));
    });
  }

  _getFullCaption(caption) {
    return [caption.title, caption.content, caption.hashtags].filter(Boolean).join('\n\n');
  }

  _insertEmoji(emoji) {
    const input = this.element.querySelector('[name="content"]');
    if (!input) return;
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    input.value = `${input.value.slice(0, start)}${emoji}${input.value.slice(end)}`;
    input.focus();
    input.setSelectionRange(start + emoji.length, start + emoji.length);
    publisherStore.updateCaption('content', input.value);
    this._updateCounter();
  }

  /** Ajoute un hashtag suggéré sans doublon (gestion Instagram des tags). */
  _appendHashtag(tag) {
    const input = this.element?.querySelector?.('[name="hashtags"]');
    if (!input || !tag) return;
    const value = String(input.value || '').trim();
    const existing = value.split(/\s+/).filter(Boolean);
    if (existing.some(item => item.toLowerCase() === tag.toLowerCase())) return;
    input.value = value ? `${value} ${tag}` : tag;
    publisherStore.updateCaption('hashtags', input.value);
    this._updateCounter();
  }

  /** Aperçu compact façon Instagram : vignette, compte et légende assemblée. */
  _updateCaptionPreview() {
    const card = this.element?.querySelector?.('[data-caption-preview]');
    if (!card) return;
    const caption = publisherStore.draft.caption || {};
    const text = this._getFullCaption(caption);

    const textEl = card.querySelector?.('[data-preview-caption]');
    if (textEl) textEl.textContent = text || 'Votre légende apparaîtra ici…';
    const accountEl = card.querySelector?.('[data-preview-account]');
    if (accountEl) accountEl.textContent = caption.accountUsername || 'Votre compte';
    const thumbEl = card.querySelector?.('[data-preview-thumb]');
    if (thumbEl) {
      const media = (publisherStore.draft.media || [])[0] || {};
      const url = media.thumbnail_url || media.url || '';
      thumbEl.style.backgroundImage = url ? `url("${String(url).replace(/"/g, '%22')}")` : '';
    }
  }

  _updateCounter() {
    const draft = publisherStore.draft;
    const fullCaption = this._getFullCaption(draft.caption);
    const length = fullCaption.length;
    const overLimit = length > MAX_LENGTH;
    const nearLimit = length > MAX_LENGTH * 0.9 && !overLimit;

    const current = this.element.querySelector('.pce-current');
    const counter = this.element.querySelector('.pce-counter');

    if (current) current.textContent = length;
    if (counter) {
      counter.classList.toggle('over', overLimit);
      counter.classList.toggle('warning', nearLimit);
    }
    const err = this.element.querySelector('.pce-error');
    const warn = this.element.querySelector('.pce-warning');
    if (err) err.hidden = !overLimit;
    if (warn) warn.hidden = !nearLimit;
    this._updateCaptionPreview();
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

  async _handleAIAction() {
    if (this._aiRunning) return;
    const toneEl = this.element.querySelector('[data-ai-tone]');
    const lengthEl = this.element.querySelector('[data-ai-length]');
    const tone = toneEl ? toneEl.value : 'performance';
    const length = lengthEl ? lengthEl.value : 'short';

    const btn = this.element.querySelector('[data-ai-action="generate"]');
    this._aiRunning = true;
    if (btn) btn.disabled = true;
    this._showAIResult('Génération en cours…', 'busy');

    try {
      const res = await this.onAIRequest({ tone, length });
      if (res && typeof res.content === 'string' && res.content) {
        this._showAIResult('Légende générée et appliquée.', 'ok');
      } else if (res && typeof res === 'object') {
        this._showAIResult('Réponse vide : rien à appliquer.', 'warn');
      } else {
        this._showAIResult('Aucune réponse du service.', 'warn');
      }
    } catch (error) {
      this._showAIResult(error?.message || 'Génération impossible.', 'err');
    } finally {
      this._aiRunning = false;
      if (btn) btn.disabled = !this.aiAvailable;
    }
  }

  _showAIResult(text, kind = '') {
    const result = this.element.querySelector('[data-ai-result]');
    if (!result) return;
    result.hidden = false;
    result.dataset.kind = kind;
    result.textContent = text;
  }

  async _openAccountSelector() {
    const panel = this.element.querySelector('[data-account-panel]');
    const btn = this.element.querySelector('[data-action="select-account"]');
    if (panel && !panel.hidden) {
      panel.hidden = true;
      return;
    }
    if (!this.instagramAccounts.length) {
      this._accountLoading = true;
      btn.disabled = true;
      try {
        const res = await getMetaInstagramAccount();
        const account = res?.data?.platform ? res.data : res;
        this.instagramAccounts = account?.platform ? [account] : [];
        this._syncAccountPresentation(account);
      } catch (e) {
        console.error('[PublisherCaptionEditor] Erreur chargement compte Instagram:', e);
        this.instagramAccounts = [];
      } finally {
        this._accountLoading = false;
        btn.disabled = false;
      }
    }
    this._updateAccountUI();
    if (panel) panel.hidden = false;
    this._renderAccountList();
  }

  async _loadInstagramAccount() {
    try {
      const res = await getMetaInstagramAccount();
      const account = res?.data?.platform ? res.data : res;
      this.instagramAccounts = account?.platform ? [account] : [];
      this._syncAccountPresentation(account);
      this._updateAccountUI();
    } catch (e) {
      console.error('[PublisherCaptionEditor] Erreur chargement compte Instagram:', e);
      this.instagramAccounts = [];
      this._updateAccountUI();
    }
  }

  _syncAccountPresentation(account) {
    const username = account?.username || account?.account_name;
    if (!username || publisherStore.draft.caption.accountUsername === username) return;
    publisherStore.draft.caption.accountUsername = username;
    publisherStore._notify();
  }

  _updateAccountUI() {
    const btn = this.element.querySelector('[data-action="select-account"]');
    if (!btn) return;
    const account = this.instagramAccounts[0];
    if (account) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
        </svg>
        <span>${this._esc(account.username || account.account_name || account.platform_account_id)}</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      `;
    } else {
      btn.disabled = false;
      btn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
        </svg>
        <span>Choisir un compte Instagram</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      `;
    }
  }

  _renderAccountList() {
    const list = this.element.querySelector('[data-account-list]');
    const empty = this.element.querySelector('[data-account-empty]');
    if (!list) return;
    list.innerHTML = this.instagramAccounts.map(account => {
      const accountId = account.platform_account_id || account.username;
      const selected = this.instagramSelectedIds.includes(accountId);
      return `
        <button type="button" class="pce-account-item ${selected ? 'selected' : ''}" data-account-id="${this._esc(accountId)}">
          <span>${this._esc(account.username || account.account_name || accountId)}</span>
          <span>${this._esc(account.account_name || '')}</span>
        </button>
      `;
    }).join('');
    this.element.querySelectorAll('[data-account-id]').forEach(btn => {
      btn.addEventListener('click', () => this._selectAccount(btn.dataset.accountId));
    });
  }

  _selectAccount(accountId) {
    const idx = this.instagramSelectedIds.indexOf(accountId);
    if (idx >= 0) {
      this.instagramSelectedIds.splice(idx, 1);
    } else {
      this.instagramSelectedIds.push(accountId);
    }
    this._renderAccountList();
  }

  _confirmAccountSelection() {
    if (!this.instagramSelectedIds.length) return;
    const accountId = this.instagramSelectedIds[0];
    publisherStore.updateCaption('accountId', accountId);
    const account = this.instagramAccounts.find(item => String(item.platform_account_id || item.username) === String(accountId));
    this._syncAccountPresentation(account);
    const panel = this.element.querySelector('[data-account-panel]');
    if (panel) panel.hidden = true;
  }

  destroy() {
    if (this._unsubscribeStore) this._unsubscribeStore();
    if (this.element && this.element.parentNode) this.element.parentNode.removeChild(this.element);
  }

  _esc(text) {
    return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
}

export function createPublisherCaptionEditor(options) {
  return new PublisherCaptionEditor(options);
}
