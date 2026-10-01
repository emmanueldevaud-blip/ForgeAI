import { authStore } from '../stores/auth.js';
import { sendAIMessage, listAIConversations, getAIConversation } from '../services/maintenanceApi.js';
import { getDevelopmentStatus, commitDevelopment, deployDevelopment } from '../services/developmentApi.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';

function formatTime(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

const TASK_STATUS_LABELS = {
  pending: 'En attente',
  analyzing: 'Analyse...',
  planning: 'Planification...',
  developing: 'Exécution...',
  testing: 'Tests...',
  fixing: 'Correction...',
  ready_for_review: 'Vérification...',
  committed: 'Commit créé',
  pushed: 'Push effectué',
  deployed: 'Déployé',
  failed: 'Échec',
  cancelled: 'Annulé',
};

const TASK_STATUS_CLASSES = {
  failed: 'is-danger',
  cancelled: 'is-muted',
  ready_for_review: 'is-success',
  committed: 'is-success',
  pushed: 'is-success',
  deployed: 'is-success',
  analyzing: 'is-running',
  planning: 'is-running',
  developing: 'is-running',
  testing: 'is-running',
  fixing: 'is-running',
};

const MODES = {
  assistant: {
    title: '🤖 Assistant IA',
    placeholder: 'Posez votre question...',
  },
  development: {
    title: '🛠 Développement',
    placeholder: 'Décrivez la demande de développement...',
  },
};

export class AIAssistantPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.conversations = [];
    this.isSending = false;
    this.isActionRunning = false;
    this.mode = 'assistant';
    this.modes = {
      assistant: { conversationId: null, messages: [] },
      development: { conversationId: null, messages: [] },
    };
    this.devStatus = null;
    this.canDevelop = false;
    this.canCommit = false;
    this.canDeploy = false;
    this.confirmDialog = null;
  }

  async initialize() {}

  async loadData() {
    await this._loadConversations();
    this._renderConversationList();
  }

  _state() {
    return this.modes[this.mode];
  }

  async _loadConversations() {
    try {
      const r = await listAIConversations({});
      this.conversations = r.items || [];
    } catch (e) { this.conversations = []; }
  }

  _visibleConversations() {
    return this.conversations.filter((c) =>
      this.mode === 'development' ? c.module === 'development' : c.module !== 'development'
    );
  }

  _renderConversationList() {
    if (!this.element) return;
    const list = this.element.querySelector('[data-conversations]');
    if (!list) return;

    const items = this._visibleConversations();
    if (items.length === 0) {
      list.innerHTML = '<p class="empty-message">Aucune conversation</p>';
      return;
    }

    const currentId = this._state().conversationId;
    list.innerHTML = items.map(c => `
      <div class="conversation-item ${c.id === currentId ? 'conversation-item--active' : ''}" data-conv-id="${c.id}">
        <div class="conversation-title">${escapeHtml(c.title || 'Sans titre')}</div>
        <div class="conversation-meta">${c.module || ''} - ${formatTime(c.created_at)}</div>
      </div>
    `).join('');

    list.querySelectorAll('.conversation-item').forEach(el => {
      el.addEventListener('click', () => this._loadConversation(parseInt(el.dataset.convId)));
    });
  }

  async _loadConversation(id) {
    try {
      const r = await getAIConversation(id);
      const state = this._state();
      state.conversationId = id;
      state.messages = r.messages || [];
      this._renderMessages();
      this._renderConversationList();
    } catch (e) {
      console.error('Erreur chargement conversation:', e);
    }
  }

  _welcomeHtml() {
    if (this.mode === 'development') {
      return `
        <div class="ai-welcome">
          <div class="ai-welcome-icon">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
          </div>
          <h3>Agent Développement</h3>
          <p>Décrivez la demande : analyse, correction de bug, fonctionnalité, fichier à étudier…</p>
          <div class="ai-suggestions">
            <button class="ai-suggestion-btn" data-suggestion="Analyse le problème de la page Bâtiments.">Analyse un problème</button>
            <button class="ai-suggestion-btn" data-suggestion="Corrige cette erreur.">Corrige une erreur</button>
            <button class="ai-suggestion-btn" data-suggestion="Ajoute cette fonctionnalité.">Ajoute une fonctionnalité</button>
            <button class="ai-suggestion-btn" data-suggestion="Analyse ce fichier.">Analyse un fichier</button>
          </div>
        </div>
      `;
    }

    return `
      <div class="ai-welcome">
        <div class="ai-welcome-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z"/>
            <path d="M10 21v1a2 2 0 0 0 4 0v-1"/>
            <circle cx="10" cy="9" r="1" fill="currentColor"/>
            <circle cx="14" cy="9" r="1" fill="currentColor"/>
          </svg>
        </div>
        <h3>Assistant IA ForgeAI</h3>
        <p>Posez vos questions sur la maintenance, les équipements, ou tout autre sujet lié au module.</p>
        <div class="ai-suggestions">
          <button class="ai-suggestion-btn" data-suggestion="Résume les demandes de maintenance ouvertes">Demandes ouvertes</button>
          <button class="ai-suggestion-btn" data-suggestion="Quels équipements sont en panne ?">Équipements en panne</button>
          <button class="ai-suggestion-btn" data-suggestion="Liste les maintenances préventives à venir">Préventif à venir</button>
          <button class="ai-suggestion-btn" data-suggestion="Quels sont les coûts de maintenance ce mois ?">Coûts du mois</button>
        </div>
      </div>
    `;
  }

  _renderMessages() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-messages]');
    if (!container) return;

    const state = this._state();

    if (state.messages.length === 0) {
      container.innerHTML = this._welcomeHtml();
      container.querySelectorAll('.ai-suggestion-btn').forEach(btn => {
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

    container.innerHTML = state.messages.map(m => `
      <div class="ai-message ai-message--${m.role}">
        <div class="ai-message-avatar">
          ${m.role === 'user' ? '👤' : '🤖'}
        </div>
        <div class="ai-message-content">
          <div class="ai-message-text">${escapeHtml(m.content)}</div>
          <div class="ai-message-time">${formatTime(m.created_at)}</div>
        </div>
      </div>
    `).join('');

    container.scrollTop = container.scrollHeight;
  }

  async _sendMessage() {
    if (this.isSending) return;

    const input = this.element.querySelector('[data-ai-input]');
    if (!input) return;

    const message = input.value.trim();
    if (!message) return;

    const state = this._state();
    this.isSending = true;
    input.value = '';

    const sendBtn = this.element.querySelector('[data-action="send"]');
    if (sendBtn) sendBtn.disabled = true;

    state.messages.push({ role: 'user', content: message, created_at: new Date().toISOString() });
    this._renderMessages();

    state.messages.push({ role: 'assistant', content: 'Réflexion en cours...', created_at: new Date().toISOString() });
    this._renderMessages();

    try {
      const payload = { message, conversation_id: state.conversationId };
      if (this.mode === 'development') payload.module = 'development';

      const r = await sendAIMessage(payload);

      state.messages.pop();
      state.messages.push({
        role: 'assistant',
        content: r.response,
        created_at: new Date().toISOString(),
      });

      state.conversationId = r.conversation_id;
      await this._loadConversations();
      if (this.mode === 'development') await this._refreshDevStatus();
    } catch (e) {
      state.messages.pop();
      state.messages.push({
        role: 'assistant',
        content: this._errorText(e, 'Désolé, une erreur est survenue. Veuillez réessayer.'),
        created_at: new Date().toISOString(),
      });
    }

    this._renderMessages();
    this._renderConversationList();
    this.isSending = false;
    if (sendBtn) sendBtn.disabled = false;
  }

  // ------------------------------------------------------------------ #
  // Sélecteur de mode
  // ------------------------------------------------------------------ #

  _setMode(mode) {
    if (!MODES[mode] || mode === this.mode) return;
    if (mode === 'development' && !this.canDevelop) return;

    this.mode = mode;

    this.element.querySelectorAll('.ai-mode-btn').forEach((btn) => {
      const active = btn.dataset.mode === mode;
      btn.classList.toggle('ai-mode-btn--active', active);
      btn.setAttribute('aria-selected', String(active));
    });

    const input = this.element.querySelector('[data-ai-input]');
    if (input) input.placeholder = MODES[mode].placeholder;

    const title = this.element.querySelector('[data-mode-title]');
    if (title) title.textContent = MODES[mode].title;

    this._renderConversationList();
    this._renderMessages();
    this._renderDevStatus();

    if (mode === 'development' && !this.devStatus) this._refreshDevStatus();
  }

  // ------------------------------------------------------------------ #
  // État Git + tâche de développement
  // ------------------------------------------------------------------ #

  async _refreshDevStatus() {
    try {
      this.devStatus = await getDevelopmentStatus();
    } catch (e) {
      this.devStatus = { unavailable: true, error: this._errorText(e) };
    }
    this._renderDevStatus();
  }

  _renderDevStatus() {
    if (!this.element) return;
    const box = this.element.querySelector('[data-dev-status]');
    if (!box) return;

    const visible = this.mode === 'development' && this.canDevelop;
    box.hidden = !visible;
    if (!visible) {
      box.innerHTML = '';
      return;
    }

    const s = this.devStatus;
    if (!s) {
      box.innerHTML = '<span class="ai-status-muted">Chargement du statut...</span>';
      return;
    }

    if (s.unavailable) {
      box.innerHTML = `<span class="ai-status-muted" title="${escapeHtml(s.error || '')}">Statut indisponible</span>`;
      return;
    }

    const git = s.git || {};
    let html = '';

    if (git.error) {
      html += `
        <div class="ai-status-item">
          <span class="ai-status-label">Git</span>
          <span class="ai-status-muted" title="${escapeHtml(git.error)}">Indisponible dans cet environnement</span>
        </div>`;
    } else {
      const count = (git.modified || []).length + (git.added || []).length
        + (git.deleted || []).length + (git.untracked || []).length;
      html += `
        <div class="ai-status-item"><span class="ai-status-label">Git</span></div>
        <div class="ai-status-item"><span class="ai-status-label">Branche</span> ${escapeHtml(git.branch || '—')}</div>
        <div class="ai-status-item"><span class="ai-status-label">Modifications</span> ${count === 0 ? 'Aucune' : `${count} fichier${count > 1 ? 's' : ''} modifié${count > 1 ? 's' : ''}`}</div>
        <div class="ai-status-item"><span class="ai-status-label">Commit</span> ${git.clean ? 'À jour' : 'Non effectué'}</div>`;
    }

    if (s.task) {
      const t = s.task;
      const label = TASK_STATUS_LABELS[t.status] || t.status;
      const cls = TASK_STATUS_CLASSES[t.status] || 'is-pending';
      html += `
        <div class="ai-status-item ai-status-task">
          <span class="ai-status-label">🛠 Développement</span>
          <span class="ai-status-badge ${cls}">${escapeHtml(label)}</span>
          <span class="ai-status-title" title="${escapeHtml(t.title || '')}">${escapeHtml(t.title || '')}</span>
        </div>`;
    }

    box.innerHTML = html;
  }

  // ------------------------------------------------------------------ #
  // Actions : Commit / Déployer
  // ------------------------------------------------------------------ #

  _errorText(error, fallback = 'Erreur inconnue') {
    const detail = error?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => d?.msg || JSON.stringify(d)).join(' — ');
    }
    return error?.message || fallback;
  }

  _setActionStatus(text, kind = '') {
    const el = this.element?.querySelector('[data-action-status]');
    if (!el) return;
    el.textContent = text;
    el.className = `ai-action-status${kind ? ` ai-action-status--${kind}` : ''}`;
  }

  _setActionBusy(kind, busy) {
    const btn = this.element?.querySelector(`[data-action="${kind}"]`);
    if (btn) btn.disabled = busy;
    this.isActionRunning = busy;
  }

  _commitMessage() {
    const task = this.devStatus?.task;
    const base = task?.title || 'Mise à jour via Assistant IA';
    return base.length > 72 ? `${base.slice(0, 72)}…` : base;
  }

  _pendingFiles() {
    const git = this.devStatus?.git;
    if (!git || git.error) return null;
    return [
      ...(git.modified || []),
      ...(git.added || []),
      ...(git.deleted || []),
      ...(git.untracked || []),
    ];
  }

  async _handleCommit() {
    if (!this.canCommit || this.isActionRunning) return;
    if (!this.devStatus) await this._refreshDevStatus();

    const message = this._commitMessage();
    const files = this._pendingFiles();
    let text = `Créer un commit avec les modifications actuelles ?\n\nMessage : ${message}`;
    if (files === null) {
      text += '\n\nFichiers : indisponibles (Git non disponible dans cet environnement).';
    } else if (files.length === 0) {
      text += '\n\nAucune modification détectée.';
    } else {
      const shown = files.slice(0, 15).map((f) => `• ${f}`).join('\n');
      text += `\n\nFichiers (${files.length}) :\n${shown}${files.length > 15 ? '\n…' : ''}`;
    }

    this.confirmDialog?.destroy();
    this.confirmDialog = new ConfirmDialog({
      onConfirm: () => this._doCommit(message),
    });
    this.confirmDialog.open({
      title: 'Créer un commit',
      message: text,
      confirmText: 'Confirmer le commit',
      cancelText: 'Annuler',
      variant: 'primary',
    });
  }

  async _doCommit(message) {
    this._setActionBusy('commit', true);
    this._setActionStatus('Commit en cours...', 'muted');
    try {
      const r = await commitDevelopment({ message, confirmed: true });
      const short = typeof r?.commit_hash === 'string' ? r.commit_hash.slice(0, 7) : '';
      this._setActionStatus(short ? `✓ Commit créé (${short})` : '✓ Commit créé', 'success');
      await this._refreshDevStatus();
    } catch (e) {
      this._setActionStatus(`✗ ${this._errorText(e)}`, 'error');
    } finally {
      this._setActionBusy('commit', false);
    }
  }

  async _handleDeploy() {
    if (!this.canDeploy || this.isActionRunning) return;

    this.confirmDialog?.destroy();
    this.confirmDialog = new ConfirmDialog({
      onConfirm: () => this._doDeploy(),
    });
    this.confirmDialog.open({
      title: '⚠️ Déploiement',
      message: 'Vous êtes sur le point de déployer la version actuelle.\nCette opération agit sur la production.',
      confirmText: 'Confirmer le déploiement',
      cancelText: 'Annuler',
      variant: 'danger',
    });
  }

  async _doDeploy() {
    this._setActionBusy('deploy', true);
    this._setActionStatus('Déploiement en cours...', 'muted');
    try {
      await deployDevelopment({ confirmed: true });
      this._setActionStatus('✓ Déploiement terminé', 'success');
      await this._refreshDevStatus();
    } catch (e) {
      this._setActionStatus(`✗ ${this._errorText(e)}`, 'error');
    } finally {
      this._setActionBusy('deploy', false);
    }
  }

  // ------------------------------------------------------------------ #
  // Rendu
  // ------------------------------------------------------------------ #

  render() {
    this.canDevelop = authStore.hasPermission('development.execute');
    this.canCommit = authStore.hasPermission('development.commit');
    this.canDeploy = authStore.hasPermission('development.deploy');

    this.element = document.createElement('div');
    this.element.className = 'page-content ai-page';
    this.element.innerHTML = `
      <div class="ai-layout">
        <div class="ai-sidebar">
          <div class="ai-sidebar-header">
            <h3>Conversations</h3>
            <button class="btn btn-primary btn-sm" data-action="new-chat">+ Nouvelle</button>
          </div>
          <div class="ai-conversations-list" data-conversations></div>
        </div>
        <div class="ai-main">
          <div class="ai-header">
            <div class="ai-header-top">
              <h2 data-mode-title>${MODES[this.mode].title}</h2>
              <div class="ai-mode-switch" role="tablist" aria-label="Mode de l'assistant">
                <button type="button" class="ai-mode-btn ai-mode-btn--active" role="tab" aria-selected="true" data-mode="assistant">🤖 Assistant</button>
                <button type="button" class="ai-mode-btn" role="tab" aria-selected="false" data-mode="development" ${this.canDevelop ? '' : 'hidden'}>🛠 Développement</button>
              </div>
            </div>
          </div>
          <div class="ai-actions">
            <div class="ai-status" data-dev-status hidden></div>
            <div class="ai-action-buttons">
              ${this.canCommit ? '<button type="button" class="btn btn-secondary btn-sm" data-action="commit">💾 Commit</button>' : ''}
              ${this.canDeploy ? '<button type="button" class="btn btn-danger btn-sm" data-action="deploy">🚀 Déployer</button>' : ''}
            </div>
            <span class="ai-action-status" data-action-status role="status"></span>
          </div>
          <div class="ai-messages" data-messages></div>
          <div class="ai-input-area">
            <textarea class="ai-input" data-ai-input placeholder="${MODES[this.mode].placeholder}" rows="2"></textarea>
            <button class="btn btn-primary" data-action="send">Envoyer</button>
          </div>
        </div>
      </div>
    `;

    this.element.querySelector('[data-action="new-chat"]')?.addEventListener('click', () => {
      const state = this._state();
      state.conversationId = null;
      state.messages = [];
      this._renderMessages();
      this._renderConversationList();
    });

    this.element.querySelector('[data-action="send"]')?.addEventListener('click', () => this._sendMessage());
    this.element.querySelector('[data-action="commit"]')?.addEventListener('click', () => this._handleCommit());
    this.element.querySelector('[data-action="deploy"]')?.addEventListener('click', () => this._handleDeploy());

    this.element.querySelectorAll('.ai-mode-btn').forEach((btn) => {
      btn.addEventListener('click', () => this._setMode(btn.dataset.mode));
    });

    const input = this.element.querySelector('[data-ai-input]');
    if (input) {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          this._sendMessage();
        }
      });
    }

    return this.element;
  }

  destroy() {
    this.confirmDialog?.destroy();
    this.confirmDialog = null;
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createAIAssistantPage(router) { return new AIAssistantPage(router); }
