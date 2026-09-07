import { GroupForm } from './GroupForm.js';

export class GroupModal {
  constructor(options = {}) {
    this.onSubmit = options.onSubmit || (() => {});
    this.onClose = options.onClose || (() => {});

    this.element = null;
    this.overlay = null;
    this.form = null;
    this.currentMode = 'create-group';
    this.currentGroup = null;
  }

  open(options = {}) {
    this.currentMode = options.mode || 'create-group';
    this.currentGroup = options.group || null;

    this._createModal();
    this._renderForm();

    document.body.appendChild(this.overlay);

    requestAnimationFrame(() => {
      this.overlay.classList.add('open');
      this.element.classList.add('open');
    });

    this._handleKeydown = this._handleKeydown.bind(this);
    this._handleOverlayClick = this._handleOverlayClick.bind(this);

    document.addEventListener('keydown', this._handleKeydown);
    this.overlay.addEventListener('click', this._handleOverlayClick);
  }

  _createModal() {
    this.overlay = document.createElement('div');
    this.overlay.className = 'modal-overlay';

    this.element = document.createElement('div');
    this.element.className = 'modal';
    this.element.setAttribute('role', 'dialog');
    this.element.setAttribute('aria-modal', 'true');

    this.modalContent = document.createElement('div');
    this.modalContent.className = 'modal-content';

    this.element.appendChild(this.modalContent);
    this.overlay.appendChild(this.element);
  }

  _renderForm() {
    const title = this.currentMode === 'edit-group'
      ? 'Modifier le groupe'
      : 'Nouveau groupe';

    this.modalContent.innerHTML = `
      <div class="modal-header">
        <h2 id="modal-title">${title}</h2>

        <button
          type="button"
          class="modal-close"
          aria-label="Fermer"
          data-action="close"
        >
          <svg width="24" height="24" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>

      <div class="modal-body" data-modal-body></div>
    `;

    this.modalContent
      .querySelector('[data-action="close"]')
      .addEventListener('click', () => this.close());

    const body = this.modalContent.querySelector('[data-modal-body]');

    this.form = new GroupForm({
      mode: this.currentMode,
      group: this.currentGroup,
      onSubmit: (data, isEdit) => this.onSubmit(data, isEdit),
      onClose: () => this.close(),
    });

    body.appendChild(this.form.render());
  }

  close() {
    if (!this.overlay) return;

    document.removeEventListener('keydown', this._handleKeydown);
    this.overlay.removeEventListener('click', this._handleOverlayClick);

    this.overlay.classList.remove('open');
    this.element.classList.remove('open');

    setTimeout(() => {
      this.overlay?.remove();

      this.overlay = null;
      this.element = null;
      this.form = null;

      this.onClose();
    }, 200);
  }

  _handleKeydown(e) {
    if (e.key === 'Escape') {
      this.close();
    }
  }

  _handleOverlayClick(e) {
    if (e.target === this.overlay) {
      this.close();
    }
  }

  destroy() {
    this.close();
  }
}
