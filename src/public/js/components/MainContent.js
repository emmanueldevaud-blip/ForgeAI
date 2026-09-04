export class MainContent {
  constructor(options = {}) {
    this.loading = false;
    this.error = null;
    this.content = null;
    this.emptyState = false;
    this.element = null;
  }

  setLoading(loading) {
    this.loading = loading;
    this._renderLoading();
  }

  setError(error) {
    this.error = error;
    this.loading = false;
    this._renderError();
  }

  setContent(content) {
    this.content = content;
    this.error = null;
    this.loading = false;
    this.emptyState = false;
    this._renderContent();
  }

  setEmptyState(message, action = null) {
    this.emptyState = true;
    this.content = null;
    this.error = null;
    this.loading = false;
    this._renderEmptyState(message, action);
  }

  clear() {
    this.content = null;
    this.error = null;
    this.loading = false;
    this.emptyState = false;
    this._renderEmpty();
  }

  _renderLoading() {
    if (!this.element) return;
    this.element.innerHTML = `
      <div class="main-content-loading" role="status" aria-live="polite">
        <div class="spinner"></div>
        <p>Chargement...</p>
      </div>
    `;
  }

  _renderError() {
    if (!this.element) return;
    this.element.innerHTML = `
      <div class="main-content-error" role="alert">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        <h2>Erreur</h2>
        <p>${this._escapeHtml(this.error?.message || this.error || 'Une erreur est survenue')}</p>
        <button class="btn btn-primary" data-action="retry">Réessayer</button>
      </div>
    `;
  }

  _renderContent() {
    if (!this.element) return;
    this.element.innerHTML = '';
    if (this.content instanceof Node) {
      this.element.appendChild(this.content);
    } else if (typeof this.content === 'string') {
      this.element.innerHTML = this.content;
    }
  }

  _renderEmptyState(message, action) {
    if (!this.element) return;
    this.element.innerHTML = `
      <div class="main-content-empty">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"></rect><path d="M9 12h6"></path><path d="M12 9v6"></path></svg>
        <h2>Contenu vide</h2>
        <p>${this._escapeHtml(message)}</p>
        ${action ? `<button class="btn btn-primary" data-action="empty-action">${this._escapeHtml(action.label)}</button>` : ''}
      </div>
    `;
    if (action) {
      this.element.querySelector('[data-action="empty-action"]')?.addEventListener('click', action.handler);
    }
  }

  _renderEmpty() {
    if (!this.element) return;
    this.element.innerHTML = '';
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  mount(container) {
    this.element = container;
    this.element.className = 'main-content';
    this.element.setAttribute('role', 'main');
    this._renderEmpty();
    return this;
  }

  destroy() {
    if (this.element) {
      this.element.innerHTML = '';
    }
  }
}