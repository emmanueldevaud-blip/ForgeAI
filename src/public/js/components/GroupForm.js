export class GroupForm {
  constructor(options = {}) {
    this.mode = options.mode || 'create-group';
    this.group = options.group || null;
    this.onSubmit = options.onSubmit || (() => {});
    this.onClose = options.onClose || (() => {});
    this.element = null;
  }

  render() {
    this.element = document.createElement('form');
    this.element.className = 'user-form';

    const isEdit = this.mode === 'edit-group';

    this.element.innerHTML = `
      <div class="form-group">
        <label for="group-name">Nom <span class="required">*</span></label>
        <input
          type="text"
          id="group-name"
          name="name"
          class="form-input"
          value="${this._escapeHtml(this.group?.name || '')}"
          required
          maxlength="100"
        >
      </div>

      <div class="form-group">
        <label for="group-description">Description</label>
        <textarea
          id="group-description"
          name="description"
          class="form-input"
          rows="4"
          maxlength="500"
        >${this._escapeHtml(this.group?.description || '')}</textarea>
      </div>

      ${isEdit ? `
        <div class="form-group">
          <label for="group-code">Code</label>
          <input
            type="text"
            id="group-code"
            class="form-input"
            value="${this._escapeHtml(this.group?.code || '')}"
            disabled
          >
        </div>

        <div class="form-group form-checkbox">
          <label>
            <input
              type="checkbox"
              name="is_active"
              ${this.group?.is_active !== false ? 'checked' : ''}
            >
            Groupe actif
          </label>
        </div>
      ` : ''}

      <div class="form-actions">
        <button type="button" class="btn btn-secondary" data-action="cancel">
          Annuler
        </button>

        <button type="submit" class="btn btn-primary">
          ${isEdit ? 'Enregistrer' : 'Créer'}
        </button>
      </div>
    `;

    this.element.addEventListener('submit', (e) => {
      e.preventDefault();
      this._handleSubmit();
    });

    this.element
      .querySelector('[data-action="cancel"]')
      ?.addEventListener('click', () => this.onClose());

    return this.element;
  }

  _handleSubmit() {
    const formData = new FormData(this.element);

    const data = {
      name: formData.get('name')?.trim() || '',
      description: formData.get('description')?.trim() || null,
    };

    if (!data.name) {
      this._showError('Le nom du groupe est obligatoire.');
      return;
    }

    if (this.mode === 'edit-group') {
      data.is_active = formData.get('is_active') === 'on';
    }

    this.onSubmit(data, this.mode === 'edit-group');
  }

  _showError(message) {
    let error = this.element.querySelector('.form-error');

    if (!error) {
      error = document.createElement('div');
      error.className = 'form-error';
      this.element
        .querySelector('.form-actions')
        .before(error);
    }

    error.textContent = message;
  }

  _escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }

  destroy() {
    this.element?.remove();
    this.element = null;
  }
}