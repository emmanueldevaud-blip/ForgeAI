export class ConfirmDialog {
  constructor(options = {}) {
    this.onConfirm = options.onConfirm || (() => {});
    this.onCancel = options.onCancel || (() => {});
    this.overlay = null;
    this.element = null;
    this.modalContent = null;
  }

  open(options = {}) {
    this._createDialog(options);

    document.body.appendChild(this.overlay);
    requestAnimationFrame(() => {
      this.overlay.classList.add('open');
      this.element.classList.add('open');
    });

    document.addEventListener('keydown', this._handleKeydown.bind(this));
    this.overlay.addEventListener('click', this._handleOverlayClick.bind(this));

    setTimeout(() => {
      const confirmBtn = this.element.querySelector('[data-action="confirm"]');
      if (confirmBtn) confirmBtn.focus();
    }, 100);
  }

  _createDialog(options) {
    const {
      title = 'Confirmation',
      message = 'Êtes-vous sûr ?',
      confirmText = 'Confirmer',
      cancelText = 'Annuler',
      variant = 'primary',
    } = options;

    const variantClasses = {
      primary: 'btn-primary',
      danger: 'btn-danger',
      warning: 'btn-warning',
    };

    this.overlay = document.createElement('div');
    this.overlay.className = 'modal-overlay confirm-dialog-overlay';

    this.element = document.createElement('div');
    this.element.className = 'modal modal--confirm';
    this.element.setAttribute('role', 'alertdialog');
    this.element.setAttribute('aria-modal', 'true');
    this.element.setAttribute('aria-labelledby', 'confirm-title');
    this.element.setAttribute('aria-describedby', 'confirm-message');

    this.modalContent = document.createElement('div');
    this.modalContent.className = 'modal-content';
    this.element.appendChild(this.modalContent);

    this.modalContent.innerHTML = `
      <div class="modal-header">
        <h2 id="confirm-title">${this._escapeHtml(title)}</h2>
        <button type="button" class="modal-close" aria-label="Fermer" data-action="cancel">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <p id="confirm-message">${this._escapeHtml(message)}</p>
      </div>
      <div class="form-actions">
        <button type="button" class="btn btn-secondary" data-action="cancel">${this._escapeHtml(cancelText)}</button>
        <button type="button" class="btn ${variantClasses[variant] || 'btn-primary'}" data-action="confirm">${this._escapeHtml(confirmText)}</button>
      </div>
    `;

    this.overlay.appendChild(this.element);

    this.modalContent.querySelector('[data-action="confirm"]').addEventListener('click', () => {
      this.onConfirm();
      this.close();
    });

    this.modalContent.querySelectorAll('[data-action="cancel"]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.onCancel();
        this.close();
      });
    });
  }

  close() {
    if (!this.overlay) return;

    this.overlay.classList.remove('open');
    this.element.classList.remove('open');

    setTimeout(() => {
      this.overlay?.remove();
      this.overlay = null;
      this.element = null;
    }, 200);
  }

  _handleKeydown(e) {
    if (e.key === 'Escape') {
      this.onCancel();
      this.close();
    } else if (e.key === 'Enter' && !e.shiftKey) {
      const confirmBtn = this.element?.querySelector('[data-action="confirm"]');
      if (confirmBtn && document.activeElement !== confirmBtn) {
        e.preventDefault();
        this.onConfirm();
        this.close();
      }
    }
  }

  _handleOverlayClick(e) {
    if (e.target === this.overlay) {
      this.onCancel();
      this.close();
    }
  }

  destroy() {
    this.close();
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}