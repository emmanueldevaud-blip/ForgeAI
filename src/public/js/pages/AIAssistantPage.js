import { authStore } from '../stores/auth.js';
import { sendAIMessage, listAIConversations, getAIConversation } from '../services/maintenanceApi.js';

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

export class AIAssistantPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.conversations = [];
    this.currentConversationId = null;
    this.messages = [];
    this.isSending = false;
  }

  async initialize() {}

  async loadData() {
    await this._loadConversations();
    this._renderConversationList();
  }

  async _loadConversations() {
    try {
      const r = await listAIConversations();
      this.conversations = r.items || [];
    } catch (e) { this.conversations = []; }
  }

  _renderConversationList() {
    if (!this.element) return;
    const list = this.element.querySelector('[data-conversations]');
    if (!list) return;

    if (this.conversations.length === 0) {
      list.innerHTML = '<p class="empty-message">Aucune conversation</p>';
      return;
    }

    list.innerHTML = this.conversations.map(c => `
      <div class="conversation-item ${c.id === this.currentConversationId ? 'conversation-item--active' : ''}" data-conv-id="${c.id}">
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
      this.currentConversationId = id;
      this.messages = r.messages || [];
      this._renderMessages();
      this._renderConversationList();
    } catch (e) {
      console.error('Erreur chargement conversation:', e);
    }
  }

  _renderMessages() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-messages]');
    if (!container) return;

    if (this.messages.length === 0) {
      container.innerHTML = `
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

    container.innerHTML = this.messages.map(m => `
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

    this.isSending = true;
    input.value = '';

    const sendBtn = this.element.querySelector('[data-action="send"]');
    if (sendBtn) sendBtn.disabled = true;

    const userMsg = { role: 'user', content: message, created_at: new Date().toISOString() };
    this.messages.push(userMsg);
    this._renderMessages();

    const thinkingMsg = { role: 'assistant', content: 'Réflexion en cours...', created_at: new Date().toISOString() };
    this.messages.push(thinkingMsg);
    this._renderMessages();

    try {
      const r = await sendAIMessage({
        message: message,
        module: 'maintenance',
        conversation_id: this.currentConversationId,
      });

      this.messages.pop();
      this.messages.push({
        role: 'assistant',
        content: r.response,
        created_at: new Date().toISOString(),
      });

      this.currentConversationId = r.conversation_id;
      await this._loadConversations();
    } catch (e) {
      this.messages.pop();
      this.messages.push({
        role: 'assistant',
        content: 'Désolé, une erreur est survenue. Veuillez réessayer.',
        created_at: new Date().toISOString(),
      });
    }

    this._renderMessages();
    this.isSending = false;
    if (sendBtn) sendBtn.disabled = false;
  }

  render() {
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
            <h2>Assistant IA</h2>
          </div>
          <div class="ai-messages" data-messages></div>
          <div class="ai-input-area">
            <textarea class="ai-input" data-ai-input placeholder="Posez votre question..." rows="2"></textarea>
            <button class="btn btn-primary" data-action="send">Envoyer</button>
          </div>
        </div>
      </div>
    `;

    this.element.querySelector('[data-action="new-chat"]')?.addEventListener('click', () => {
      this.currentConversationId = null;
      this.messages = [];
      this._renderMessages();
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

    return this.element;
  }

  destroy() {
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createAIAssistantPage(router) { return new AIAssistantPage(router); }
