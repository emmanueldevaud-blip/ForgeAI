import {
  getAiSettings,
  updateAiSettings,
  sendAiChat,
  listAiConversations,
  getAiConversation,
} from '../services/adminApi.js?v=2';

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

export class AiSettingsPage {
  constructor() {
    this.element = null;
    this.settings = null;
    this.view = 'chat';
    this.conversations = [];
    this.currentConversationId = null;
    this.messages = [];
    this.isSending = false;
    this.lastMeta = null;
  }

  async initialize() {
    const [, conversations] = await Promise.all([
      getAiSettings(),
      listAiConversations().catch(() => []),
    ]);
    this.conversations = Array.isArray(conversations)
      ? conversations
      : (conversations?.items || []);
  }

  // ------------------------------------------------------------------ #
  // Vue (sous-onglets Assistant / Paramètres)
  // ------------------------------------------------------------------ #

  _updateView() {
    if (!this.element) return;
    this.element.querySelectorAll('[data-view]').forEach((btn) => {
      const active = btn.dataset.view === this.view;
      btn.classList.toggle('btn-primary', active);
      btn.classList.toggle('btn-secondary', !active);
    });
    this.element.querySelectorAll('[data-view-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.viewPanel !== this.view;
    });
    if (this.view === 'chat') {
      this._renderConversationList();
      this._renderMessages();
    }
  }

  // ------------------------------------------------------------------ #
  // Chat
  // ------------------------------------------------------------------ #

  async _loadConversations() {
    try {
      const r = await listAiConversations();
      this.conversations = Array.isArray(r) ? r : (r?.items || []);
    } catch (e) {
      this.conversations = [];
    }
  }

  _renderConversationList() {
    if (!this.element) return;
    const list = this.element.querySelector('[data-conversations]');
    if (!list) return;

    if (this.conversations.length === 0) {
      list.innerHTML = '<p class="empty-message">Aucune conversation</p>';
      return;
    }

    list.innerHTML = this.conversations.map((c) => `
      <div class="conversation-item ${c.id === this.currentConversationId ? 'conversation-item--active' : ''}" data-conv-id="${c.id}">
        <div class="conversation-title">${escapeHtml(c.title || 'Sans titre')}</div>
        <div class="conversation-meta">${formatTime(c.created_at)}</div>
      </div>
    `).join('');

    list.querySelectorAll('.conversation-item').forEach((el) => {
      el.addEventListener('click', () => this._loadConversation(Number(el.dataset.convId)));
    });
  }

  async _loadConversation(id) {
    try {
      const r = await getAiConversation(id);
      this.currentConversationId = id;
      this.messages = (r.messages || []).map((m) => ({
        role: m.role,
        content: m.content,
        created_at: m.created_at,
      }));
      this._renderMessages();
      this._renderConversationList();
    } catch (e) {
      console.error('Erreur chargement conversation:', e);
    }
  }

  _renderMeta() {
    if (!this.element) return;
    const meta = this.element.querySelector('[data-chat-meta]');
    if (!meta) return;
    if (!this.lastMeta) {
      meta.textContent = '';
      return;
    }
    const m = this.lastMeta;
    const tokens = (m.tokens_input != null && m.tokens_output != null)
      ? ` · ${m.tokens_input}→${m.tokens_output} tokens`
      : '';
    meta.textContent = `Dernier appel : ${m.provider} · ${m.model} · ${m.latency}s${tokens}`;
  }

  _renderMessages() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-messages]');
    if (!container) return;

    if (this.messages.length === 0) {
      container.innerHTML = `
        <div class="ai-welcome">
          <div class="ai-welcome-icon">✦</div>
          <h3>Assistant IA ForgeAI</h3>
          <p>Posez vos questions : fonctionnalités de l'ERP, chiffrage, métrés, maintenance, organisation…</p>
          <div class="ai-suggestions">
            <button class="ai-suggestion-btn" data-suggestion="Explique-moi les fonctionnalités principales de ForgeAI">Fonctionnalités</button>
            <button class="ai-suggestion-btn" data-suggestion="Comment organiser un métré efficacement ?">Organiser un métré</button>
            <button class="ai-suggestion-btn" data-suggestion="Donne-moi 3 conseils pour un chiffrage rigoureux">Conseils chiffrage</button>
            <button class="ai-suggestion-btn" data-suggestion="Résume le rôle de l'AI Gateway dans ForgeAI">AI Gateway</button>
          </div>
        </div>
      `;
      container.querySelectorAll('.ai-suggestion-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const input = this.element.querySelector('[data-ai-input]');
          if (input) {
            input.value = btn.dataset.suggestion;
            this._sendMessage();
          }
        });
      });
      return;
    }

    container.innerHTML = this.messages.map((m) => `
      <div class="ai-message ai-message--${m.role}">
        <div class="ai-message-avatar">${m.role === 'user' ? '👤' : '🤖'}</div>
        <div class="ai-message-content">
          <div class="ai-message-text">${escapeHtml(m.content)}</div>
          <div class="ai-message-time">${formatTime(m.created_at)}</div>
        </div>
      </div>
    `).join('');

    container.scrollTop = container.scrollHeight;
  }

  async _sendMessage() {
    if (this.isSending || !this.element) return;

    const input = this.element.querySelector('[data-ai-input]');
    if (!input) return;

    const message = input.value.trim();
    if (!message) return;

    const taskSelect = this.element.querySelector('[data-task-type]');
    const taskType = taskSelect ? taskSelect.value : 'general';

    this.isSending = true;
    input.value = '';

    const sendBtn = this.element.querySelector('[data-action="send"]');
    if (sendBtn) sendBtn.disabled = true;

    this.messages.push({ role: 'user', content: message, created_at: new Date().toISOString() });
    this.messages.push({ role: 'assistant', content: 'Réflexion en cours…', created_at: new Date().toISOString() });
    this._renderMessages();

    try {
      const r = await sendAiChat({
        message,
        conversation_id: this.currentConversationId,
        task_type: taskType,
      });

      this.messages.pop();
      this.messages.push({
        role: 'assistant',
        content: r.response,
        created_at: new Date().toISOString(),
      });
      this.currentConversationId = r.conversation_id;
      this.lastMeta = {
        provider: r.provider,
        model: r.model,
        latency: r.latency,
        tokens_input: r.tokens_input,
        tokens_output: r.tokens_output,
      };
      this._renderMeta();
      await this._loadConversations();
    } catch (error) {
      this.messages.pop();
      this.messages.push({
        role: 'assistant',
        content: error.data?.detail || error.message || 'Erreur lors de l\'appel IA. Veuillez réessayer.',
        created_at: new Date().toISOString(),
      });
    }

    this._renderMessages();
    this._renderConversationList();
    this.isSending = false;
    if (sendBtn) sendBtn.disabled = false;
  }

  _bindChat() {
    this.element.querySelector('[data-action="new-chat"]')?.addEventListener('click', () => {
      this.currentConversationId = null;
      this.messages = [];
      this.lastMeta = null;
      this._renderMessages();
      this._renderMeta();
      this._renderConversationList();
    });

    this.element.querySelector('[data-action="send"]')?.addEventListener('click', () => this._sendMessage());

    const input = this.element.querySelector('[data-ai-input]');
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this._sendMessage();
        }
      });
    }
  }

  // ------------------------------------------------------------------ #
  // Paramètres (formulaire existant)
  // ------------------------------------------------------------------ #

  _providerCard(prefix, title) {
    return `
      <div class="card" style="margin-top:1rem;">
        <div class="card-header">
          <h2>${title}</h2>
        </div>
        <div class="card-body">
          <div class="form-row">
            <label class="checkbox-label"><input name="${prefix}_enabled" type="checkbox"> Fournisseur activé</label>
            <label></label>
          </div>
          <div class="form-row">
            <label><span>Clé API</span><input name="${prefix}_api_key" type="password" autocomplete="new-password" placeholder="Non configurée"></label>
            <label><span>Modèle</span><input name="${prefix}_model" maxlength="100" placeholder="Catalogue par défaut"></label>
          </div>
          <div class="form-row">
            <label><span>Statut de la clé</span><span class="text-muted" data-key-status="${prefix}"></span></label>
            <label><span>URL de base</span><input name="${prefix}_base_url" maxlength="255"></label>
          </div>
        </div>
      </div>
    `;
  }

  _updateKeyStatuses() {
    const form = this.element.querySelector('[data-ai-form]');
    if (!form) return;
    ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
      const configured = !!this.settings?.[prefix]?.api_key_configured;
      const input = form.elements[`${prefix}_api_key`];
      const status = this.element.querySelector(`[data-key-status="${prefix}"]`);
      if (input) {
        input.placeholder = configured
          ? 'Clé configurée — laisser vide pour conserver'
          : 'Non configurée';
      }
      if (status) {
        status.textContent = configured
          ? '✓ Clé enregistrée (masquée pour sécurité)'
          : 'Aucune clé enregistrée';
        status.style.color = configured ? 'var(--color-success)' : '';
      }
    });
  }

  _setMessage(text) {
    this.element.querySelectorAll('[data-ai-message]').forEach((el) => {
      el.textContent = text;
    });
  }

  _bindSettingsForm() {
    const form = this.element.querySelector('[data-ai-form]');
    if (!form) return;
    const s = this.settings || {};

    const setValue = (name, value) => { form.elements[name].value = value ?? ''; };
    form.elements.enabled.checked = s.enabled !== false;
    form.elements.default_provider.value = s.default_provider || 'auto';
    setValue('default_model', s.default_model || 'auto');
    setValue('provider_order', s.provider_order || 'groq,gemini,openrouter');
    setValue('timeout_seconds', s.timeout_seconds ?? 30);
    setValue('max_retries', s.max_retries ?? 2);
    setValue('retry_backoff_seconds', s.retry_backoff_seconds ?? 1);
    ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
      form.elements[`${prefix}_enabled`].checked = s[prefix]?.enabled !== false;
      setValue(`${prefix}_model`, s[prefix]?.model);
      setValue(`${prefix}_base_url`, s[prefix]?.base_url);
    });
    this._updateKeyStatuses();

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const providerPayload = (prefix) => ({
        enabled: form.elements[`${prefix}_enabled`].checked,
        api_key: form.elements[`${prefix}_api_key`].value,
        base_url: form.elements[`${prefix}_base_url`].value,
        model: form.elements[`${prefix}_model`].value,
      });
      const payload = {
        enabled: form.elements.enabled.checked,
        default_provider: form.elements.default_provider.value,
        default_model: form.elements.default_model.value || 'auto',
        provider_order: form.elements.provider_order.value || 'groq,gemini,openrouter',
        timeout_seconds: Number(form.elements.timeout_seconds.value),
        max_retries: Number(form.elements.max_retries.value),
        retry_backoff_seconds: Number(form.elements.retry_backoff_seconds.value),
        groq: providerPayload('groq'),
        gemini: providerPayload('gemini'),
        openrouter: providerPayload('openrouter'),
      };
      try {
        this.settings = await updateAiSettings(payload);
        ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
          form.elements[`${prefix}_api_key`].value = '';
        });
        this._updateKeyStatuses();
        this._setMessage('Paramètres enregistrés. Les clés saisies sont conservées (masquées).');
      } catch (error) {
        const detail = error.data?.detail;
        const detailText = Array.isArray(detail)
          ? detail.map((item) => item?.msg || JSON.stringify(item)).join(' — ')
          : detail;
        this._setMessage(detailText || error.message || 'Erreur lors de l\'enregistrement.');
      }
    });
  }

  // ------------------------------------------------------------------ #
  // Rendu
  // ------------------------------------------------------------------ #

  render() {
    this.element = document.createElement('div');
    this.element.className = 'admin-settings-page';
    this.element.innerHTML = `
      <div style="display:flex; gap:0.5rem; margin-bottom:1rem;">
        <button type="button" class="btn btn-sm" data-view="chat">Assistant</button>
        <button type="button" class="btn btn-sm" data-view="settings">Paramètres</button>
      </div>

      <section data-view-panel="chat" ${this.view !== 'chat' ? 'hidden' : ''}>
        <div class="ai-layout" style="height:calc(100vh - 420px); min-height:360px;">
          <div class="ai-sidebar">
            <div class="ai-sidebar-header">
              <h3>Conversations</h3>
              <button class="btn btn-primary btn-sm" data-action="new-chat">+ Nouvelle</button>
            </div>
            <div class="ai-conversations-list" data-conversations></div>
          </div>
          <div class="ai-main">
            <div class="ai-header">
              <h2>Assistant IA</h2>
              <span class="text-muted" data-chat-meta style="font-size:var(--font-size-xs);"></span>
            </div>
            <div class="ai-messages" data-messages></div>
            <div class="ai-input-area">
              <select data-task-type class="form-control" style="max-width:150px;" aria-label="Type de tâche">
                <option value="general">Général</option>
                <option value="fast">Rapide</option>
                <option value="reasoning">Raisonnement</option>
                <option value="coding">Code</option>
              </select>
              <textarea class="ai-input" data-ai-input placeholder="Posez votre question… (Entrée pour envoyer)" rows="2" maxlength="4000"></textarea>
              <button class="btn btn-primary" data-action="send">Envoyer</button>
            </div>
          </div>
        </div>
      </section>

      <section data-view-panel="settings" ${this.view !== 'settings' ? 'hidden' : ''}>
        <form data-ai-form>
          <div class="card">
            <div class="card-header">
              <h2>Paramètres de l’assistant IA</h2>
              <p class="text-muted">Passerelle IA centralisée : fournisseurs, modèles et limites d’appels.</p>
            </div>
            <div class="card-body">
              <div class="form-row">
                <label class="checkbox-label"><input name="enabled" type="checkbox"> Passerelle IA activée</label>
                <label></label>
              </div>
              <div class="form-row">
                <label><span>Fournisseur par défaut</span>
                  <select name="default_provider">
                    <option value="auto">Automatique (selon l’ordre)</option>
                    <option value="groq">Groq</option>
                    <option value="gemini">Google Gemini</option>
                    <option value="openrouter">OpenRouter</option>
                  </select>
                </label>
                <label><span>Modèle par défaut</span><input name="default_model" maxlength="100" placeholder="auto"></label>
              </div>
              <div class="form-row">
                <label><span>Ordre de repli (fallback)</span><input name="provider_order" maxlength="100" placeholder="groq,gemini,openrouter"></label>
                <label></label>
              </div>
              <div class="form-row">
                <label><span>Timeout (secondes)</span><input name="timeout_seconds" type="number" min="1" max="300" step="1"></label>
                <label><span>Retries</span><input name="max_retries" type="number" min="0" max="5" step="1"></label>
              </div>
              <div class="form-row">
                <label><span>Backoff entre retries (secondes)</span><input name="retry_backoff_seconds" type="number" min="0" max="30" step="0.5"></label>
                <label></label>
              </div>
              <div class="form-actions">
                <button class="btn btn-primary" type="submit">Enregistrer</button>
                <span data-ai-message role="status"></span>
              </div>
            </div>
          </div>
          ${this._providerCard('groq', 'Groq')}
          ${this._providerCard('gemini', 'Google Gemini')}
          ${this._providerCard('openrouter', 'OpenRouter')}
          <div class="form-actions" style="margin-top:1rem;">
            <button class="btn btn-primary" type="submit">Enregistrer</button>
            <span data-ai-message role="status"></span>
          </div>
        </form>
      </section>
    `;

    this.element.querySelectorAll('[data-view]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.view = btn.dataset.view;
        this._updateView();
      });
    });

    this._bindChat();
    this._bindSettingsForm();
    this._updateView();
    this._renderMeta();
    return this.element;
  }

  onTabActivate() {
    this._loadConversations().then(() => this._renderConversationList());
  }

  destroy() {}
}

export function createAiSettingsPage() {
  return new AiSettingsPage();
}
