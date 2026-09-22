import {
  createEmailTemplate,
  deleteEmailTemplateAttachment,
  listEmailTemplates,
  listHousings,
  updateEmailTemplate,
  updateEmailTemplateAttachmentHousings,
  uploadEmailTemplateAttachment,
} from '../services/housingApi.js?v=2';

const VARIABLES = [
  'occupant_first_name', 'occupant_last_name', 'occupant_email',
  'arrival_date', 'departure_date', 'housing_name', 'housing_reference',
  'building_name', 'site_name', 'room_index', 'nb_persons', 'guest_type',
  'purpose', 'observations',
];

export class HousingEmailTemplatesPage {
  constructor() {
    this.element = null;
    this.templates = [];
    this.housings = [];
    this.editingId = null;
  }

  async initialize() {
    const [templateResponse, housingResponse] = await Promise.all([
      listEmailTemplates({ page_size: 100, is_active: null }),
      listHousings({ page_size: 1000, is_active: true }),
    ]);
    this.templates = templateResponse.items || [];
    this.housings = housingResponse.items || [];
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this._renderList();
    return this.element;
  }

  _renderList() {
    this.element.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Modèles d’e-mails</h1>
          <p class="text-muted">Créez des modèles avec variables et pièces jointes par logement.</p>
        </div>
        <button class="btn btn-primary" data-action="new-template">Nouveau modèle</button>
      </div>
      <div class="card-grid">
        ${this.templates.length === 0
          ? '<div class="card"><p class="text-muted">Aucun modèle d’e-mail.</p></div>'
          : this.templates.map(template => `
            <article class="card">
              <div class="card-header" style="display:flex;justify-content:space-between;gap:12px;">
                <div><h2>${this._escape(template.name)}</h2><p class="text-muted">${this._escape(template.template_type)}</p></div>
                <span class="badge">${template.is_active ? 'Actif' : 'Inactif'}</span>
              </div>
              <div class="card-body">
                <p><strong>Sujet :</strong> ${this._escape(template.subject)}</p>
                <p><strong>Pièces jointes :</strong> ${(template.attachments || []).length}</p>
                <div style="display:flex;gap:8px;margin-top:16px;">
                  <button class="btn btn-secondary" data-action="edit-template" data-id="${template.id}">Modifier</button>
                  <button class="btn btn-secondary" data-action="toggle-template" data-id="${template.id}">${template.is_active ? 'Désactiver' : 'Activer'}</button>
                </div>
              </div>
            </article>`).join('')}
      </div>
    `;
    this.element.querySelector('[data-action="new-template"]')?.addEventListener('click', () => this._openEditor());
    this.element.querySelectorAll('[data-action="edit-template"]').forEach(button => {
      button.addEventListener('click', () => this._openEditor(this.templates.find(t => t.id === Number(button.dataset.id))));
    });
    this.element.querySelectorAll('[data-action="toggle-template"]').forEach(button => {
      button.addEventListener('click', () => this._toggleTemplate(Number(button.dataset.id)));
    });
  }

  _openEditor(template = null) {
    this.editingId = template?.id || null;
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay open';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:1100;display:flex;align-items:center;justify-content:center;padding:16px;background:var(--color-overlay);';
    overlay.innerHTML = `
      <div class="modal-content" style="width:min(900px,100%);max-height:90vh;overflow:auto;">
        <div class="modal-header"><h2>${template ? 'Modifier' : 'Nouveau'} modèle</h2><button class="modal-close" data-close>&times;</button></div>
        <form data-template-form class="modal-body">
          <div class="form-row">
            <label><span>Nom *</span><input name="name" required maxlength="100" value="${this._attribute(template?.name)}"></label>
            <label><span>Type *</span><select name="template_type"><option value="confirmation">Confirmation</option><option value="reminder">Rappel</option><option value="custom">Personnalisé</option></select></label>
          </div>
          <label><span>Sujet *</span><input name="subject" required maxlength="200" value="${this._attribute(template?.subject)}"></label>
          <div style="margin:12px 0;display:flex;gap:6px;flex-wrap:wrap;align-items:center;"><strong>Variables :</strong>${VARIABLES.map(variable => `<button type="button" class="btn btn-sm btn-secondary" data-variable="${variable}">{{${variable}}}</button>`).join('')}</div>
          <label><span>Contenu HTML *</span><textarea name="body_html" required rows="10">${this._escape(template?.body_html)}</textarea></label>
          <label><span>Contenu texte</span><textarea name="body_text" rows="6">${this._escape(template?.body_text)}</textarea></label>
          <label class="checkbox-label"><input name="is_active" type="checkbox" ${template?.is_active !== false ? 'checked' : ''}> Modèle actif</label>
          ${template ? this._renderAttachments(template) : ''}
          <div class="modal-footer" style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px;"><button type="button" class="btn btn-secondary" data-close>Annuler</button><button class="btn btn-primary">Enregistrer</button></div>
        </form>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => overlay.remove()));
    overlay.querySelector('select[name="template_type"]').value = template?.template_type || 'confirmation';
    overlay.querySelectorAll('[data-variable]').forEach(button => button.addEventListener('click', () => {
      const field = overlay.querySelector('textarea[name="body_html"]');
      field.setRangeText(`{{${button.dataset.variable}}}`, field.selectionStart, field.selectionEnd, 'end');
      field.focus();
    }));
    overlay.querySelector('[data-template-form]').addEventListener('submit', event => this._saveTemplate(event, overlay, template));
    overlay.querySelectorAll('[data-action="upload-attachment"]').forEach(button => button.addEventListener('click', () => this._uploadAttachment(overlay, template.id)));
    overlay.querySelectorAll('[data-action="save-attachment-housings"]').forEach(button => button.addEventListener('click', () => this._saveAttachmentHousings(overlay, template.id, Number(button.dataset.id))));
    overlay.querySelectorAll('[data-action="delete-attachment"]').forEach(button => button.addEventListener('click', async () => {
      if (!window.confirm('Supprimer cette pièce jointe ?')) return;
      try {
        await deleteEmailTemplateAttachment(template.id, Number(button.dataset.id));
        overlay.remove();
        const response = await listEmailTemplates({ page_size: 100, is_active: null });
        this.templates = response.items || [];
        this._renderList();
      } catch (error) { alert(error.data?.detail || error.message || 'Erreur lors de la suppression'); }
    }));
  }

  _renderAttachments(template) {
    return `<section style="margin-top:20px;"><h3>Pièces jointes</h3>
      ${(template.attachments || []).map(attachment => `<div style="padding:10px 0;border-top:1px solid var(--color-border-light);">
        <strong>${this._escape(attachment.filename)}</strong>
        <select multiple size="3" data-attachment-housings="${attachment.id}" style="display:block;width:100%;margin:8px 0;">${this.housings.map(housing => `<option value="${housing.id}" ${(attachment.housing_ids || []).includes(housing.id) ? 'selected' : ''}>${this._escape(housing.name || housing.reference || `Logement ${housing.id}`)}</option>`).join('')}</select>
        <button type="button" class="btn btn-sm btn-secondary" data-action="save-attachment-housings" data-id="${attachment.id}">Enregistrer la catégorie</button>
        <button type="button" class="btn btn-sm btn-danger" data-action="delete-attachment" data-id="${attachment.id}">Supprimer</button>
      </div>`).join('')}
      <div style="margin-top:12px;"><input type="file" data-attachment-file multiple><select multiple size="3" data-upload-housings style="display:block;width:100%;margin:8px 0;">${this.housings.map(housing => `<option value="${housing.id}">${this._escape(housing.name || housing.reference || `Logement ${housing.id}`)}</option>`).join('')}</select><button type="button" class="btn btn-secondary" data-action="upload-attachment">Ajouter les pièces jointes</button></div>
    </section>`;
  }

  async _saveTemplate(event, overlay, template) {
    event.preventDefault();
    const form = overlay.querySelector('[data-template-form]');
    const data = Object.fromEntries(new FormData(form).entries());
    data.is_active = form.elements.is_active.checked;
    try {
      const saved = template ? await updateEmailTemplate(template.id, data) : await createEmailTemplate(data);
      if (!template) this.templates.push(saved);
      else this.templates = this.templates.map(item => item.id === saved.id ? saved : item);
      overlay.remove();
      this._renderList();
    } catch (error) { alert(error.data?.detail || error.message || 'Erreur lors de l’enregistrement'); }
  }

  async _toggleTemplate(id) {
    const template = this.templates.find(item => item.id === id);
    if (!template) return;
    try {
      const updated = await updateEmailTemplate(id, { is_active: !template.is_active });
      this.templates = this.templates.map(item => item.id === id ? updated : item);
      this._renderList();
    } catch (error) { alert(error.data?.detail || error.message); }
  }

  async _uploadAttachment(overlay, templateId) {
    const files = Array.from(overlay.querySelector('[data-attachment-file]').files || []);
    const housingIds = Array.from(overlay.querySelector('[data-upload-housings]').selectedOptions).map(option => Number(option.value));
    try {
      for (const file of files) await uploadEmailTemplateAttachment(templateId, file, housingIds);
      overlay.remove();
      const response = await listEmailTemplates({ page_size: 100, is_active: null });
      this.templates = response.items || [];
      this._renderList();
    } catch (error) { alert(error.data?.detail || error.message || 'Erreur lors de l’upload'); }
  }

  async _saveAttachmentHousings(overlay, templateId, attachmentId) {
    const select = overlay.querySelector(`[data-attachment-housings="${attachmentId}"]`);
    const housingIds = Array.from(select.selectedOptions).map(option => Number(option.value));
    try { await updateEmailTemplateAttachmentHousings(templateId, attachmentId, housingIds); alert('Catégorie enregistrée'); }
    catch (error) { alert(error.data?.detail || error.message); }
  }

  _escape(value) { const div = document.createElement('div'); div.textContent = value || ''; return div.innerHTML; }
  _attribute(value) { return this._escape(value).replace(/"/g, '&quot;'); }
  destroy() {}
}

export function createHousingEmailTemplatesPage() { return new HousingEmailTemplatesPage(); }
