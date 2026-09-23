import {
  createEmailTemplate,
  deleteEmailTemplate,
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
  'volunteer_first_name', 'volunteer_last_name', 'volunteer_email', 'scheduled_date',
];

const VARIABLE_LABELS = {
  occupant_first_name: 'Prénom occupant',
  occupant_last_name: 'Nom occupant',
  occupant_email: 'E-mail occupant',
  arrival_date: 'Date arrivée',
  departure_date: 'Date départ',
  housing_name: 'Logement',
  housing_reference: 'Référence logement',
  building_name: 'Bâtiment',
  site_name: 'Site',
  room_index: 'Chambre',
  nb_persons: 'Nombre de personnes',
  guest_type: 'Type de séjour',
  purpose: 'Motif',
  observations: 'Observations',
  volunteer_first_name: 'Prénom volontaire',
  volunteer_last_name: 'Nom volontaire',
  volunteer_email: 'E-mail volontaire',
  scheduled_date: 'Date du ménage',
  available_url: 'Lien disponible',
  unavailable_url: 'Lien indisponible',
};

const PREVIEW_VALUES = {
  occupant_first_name: 'Camille',
  occupant_last_name: 'Martin',
  occupant_email: 'camille.martin@example.com',
  arrival_date: '12/10/2026',
  departure_date: '18/10/2026',
  housing_name: '',
  housing_reference: '',
  building_name: '',
  site_name: '',
  room_index: '204',
  nb_persons: '2',
  guest_type: 'Intervenant',
  purpose: 'Mission professionnelle',
  observations: 'Merci de contacter l’accueil à votre arrivée.',
  volunteer_first_name: 'Alex',
  volunteer_last_name: 'Durand',
  volunteer_email: 'alex.durand@example.com',
  scheduled_date: '20/10/2026',
  available_url: '#disponible',
  unavailable_url: '#indisponible',
};

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
    this.element.className = 'page-content housing-page';
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
                  <button class="btn btn-danger" data-action="delete-template" data-id="${template.id}">Supprimer</button>
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
    this.element.querySelectorAll('[data-action="delete-template"]').forEach(button => {
      button.addEventListener('click', () => this._deleteTemplate(Number(button.dataset.id)));
    });
  }

  _getPreviewValues() {
    const housing = this.housings[0] || {};
    const building = housing.building?.name || housing.building || '';
    const site = housing.site?.name || housing.site || '';
    return {
      ...PREVIEW_VALUES,
      housing_name: housing.room?.name || housing.name || '',
      housing_reference: housing.room?.reference || housing.reference || '',
      building_name: building,
      site_name: site,
    };
  }

  _openEditor(template = null) {
    this.editingId = template?.id || null;
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay open';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:1100;display:flex;align-items:center;justify-content:center;padding:16px;background:var(--color-overlay);';
    overlay.innerHTML = `
      <div class="modal-content" style="width:min(900px,100%);max-height:90vh;overflow:auto;">
        <div class="modal-header"><h2>${template ? 'Modifier' : 'Nouveau'} modèle</h2><button class="modal-close" data-close aria-label="Fermer">&times;</button></div>
        <form data-template-form class="modal-body">
          <div class="form-row">
            <label><span>Nom *</span><input name="name" required maxlength="100" value="${this._attribute(template?.name)}"></label>
            <label><span>Type *</span><select name="template_type"><option value="confirmation">Confirmation réservation</option><option value="cancellation">Annulation réservation</option><option value="cleaning_invitation">Invitation ménage</option><option value="cleaning_confirmation">Confirmation ménage</option><option value="cleaning_not_selected">Volontaire non retenu</option><option value="cleaning_cancellation">Annulation ménage</option><option value="reminder">Rappel</option><option value="custom">Personnalisé</option></select></label>
          </div>
           <label><span>Sujet *</span><input name="subject" data-template-subject required maxlength="200" value="${this._attribute(template?.subject)}"></label>
           <section data-variables-panel style="margin:12px 0;padding:12px;border:1px solid var(--color-border);border-radius:8px;background:var(--color-gray-50);">
             <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;"><strong>Insérer une variable</strong><input type="search" data-variable-search placeholder="Rechercher une variable" style="min-width:220px;flex:1;max-width:320px;"></div>
             <div data-variable-buttons style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;">${VARIABLES.map(variable => `<button type="button" class="btn btn-sm btn-secondary" data-variable="${variable}" title="{{${variable}}}">${VARIABLE_LABELS[variable] || variable}</button>`).join('')}</div>
             <small data-variable-empty hidden style="display:block;margin-top:8px;color:var(--color-text-secondary);">Aucune variable trouvée.</small>
           </section>
          <label><span>Contenu HTML *</span>
            <input type="hidden" name="body_html" value="">
            <div data-rich-editor-wrapper style="border:1px solid var(--color-border);border-radius:6px;overflow:hidden;">
              <div data-rich-toolbar style="display:flex;gap:4px;flex-wrap:wrap;padding:8px;background:var(--color-gray-50);border-bottom:1px solid var(--color-border);">
                <button type="button" class="btn btn-sm btn-secondary" data-command="bold"><strong>Gras</strong></button>
                <button type="button" class="btn btn-sm btn-secondary" data-command="italic"><em>Italique</em></button>
                <button type="button" class="btn btn-sm btn-secondary" data-command="underline"><u>Souligné</u></button>
                <select data-format-block class="form-control" style="width:auto;padding:4px 8px;"><option value="p">Paragraphe</option><option value="h2">Titre</option><option value="h3">Sous-titre</option></select>
                <button type="button" class="btn btn-sm btn-secondary" data-command="insertUnorderedList">Liste</button>
                <button type="button" class="btn btn-sm btn-secondary" data-command="insertOrderedList">Liste numérotée</button>
                <button type="button" class="btn btn-sm btn-secondary" data-command="justifyLeft">Gauche</button>
                <button type="button" class="btn btn-sm btn-secondary" data-command="justifyCenter">Centrer</button>
                <button type="button" class="btn btn-sm btn-secondary" data-action="insert-link">Lien</button>
                <button type="button" class="btn btn-sm btn-secondary" data-command="removeFormat">Effacer le format</button>
              </div>
               <div data-rich-editor contenteditable="true" role="textbox" aria-multiline="true" style="min-height:240px;padding:12px;outline:none;">${template?.body_html || ''}</div>
             </div>
           </label>
           <div style="display:flex;gap:8px;margin-top:12px;">
             <button type="button" class="btn btn-secondary" data-editor-toggle>Aperçu</button>
           </div>
           <div data-template-preview hidden style="margin-top:12px;border:1px solid var(--color-border);border-radius:8px;overflow:hidden;background:#fff;"><iframe title="Aperçu du modèle" sandbox="" style="display:block;width:100%;height:360px;border:0;"></iframe></div>
            <label class="checkbox-label"><input name="is_default" type="checkbox" ${template?.is_default ? 'checked' : ''}> Utiliser comme modèle par défaut pour cette action</label>
           <label class="checkbox-label"><input name="is_active" type="checkbox" ${template?.is_active !== false ? 'checked' : ''}> Modèle actif</label>
          ${template ? this._renderAttachments(template) : ''}
          <div class="modal-footer" style="margin-top:16px;display:flex;justify-content:flex-end;gap:8px;"><button type="button" class="btn btn-secondary" data-close>Annuler</button><button class="btn btn-primary">Enregistrer</button></div>
        </form>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => overlay.remove()));
    overlay.querySelector('select[name="template_type"]').value = template?.template_type || 'confirmation';
    const editor = overlay.querySelector('[data-rich-editor]');
    const subjectInput = overlay.querySelector('[data-template-subject]');
    const preview = overlay.querySelector('[data-template-preview]');
    const previewFrame = preview.querySelector('iframe');
    const updatePreview = () => {
      const previewValues = this._getPreviewValues();
      const html = editor.innerHTML.replace(/{{\s*([\w]+)\s*}}/g, (match, variable) => previewValues[variable] ?? match);
      const subject = subjectInput.value.replace(/{{\s*([\w]+)\s*}}/g, (match, variable) => previewValues[variable] ?? match);
      previewFrame.srcdoc = `<html><head><meta charset="UTF-8"><style>body{font-family:Arial,sans-serif;color:#1f2937;padding:24px;line-height:1.5}h1{font-size:20px;margin:0 0 20px}a{color:#2563eb}</style></head><body><h1>${this._escape(subject)}</h1>${html}</body></html>`;
    };
    updatePreview();
    let savedRange = null;
    let variableTarget = editor;
    const saveRange = () => {
      const selection = window.getSelection();
      if (selection.rangeCount && editor.contains(selection.anchorNode)) savedRange = selection.getRangeAt(0).cloneRange();
    };
    editor.addEventListener('keyup', saveRange);
    editor.addEventListener('mouseup', saveRange);
    editor.addEventListener('input', updatePreview);
    editor.addEventListener('focus', () => { variableTarget = editor; });
    subjectInput.addEventListener('focus', () => { variableTarget = subjectInput; });
    subjectInput.addEventListener('input', updatePreview);
    overlay.querySelector('[data-variable-search]').addEventListener('input', event => {
      const query = event.target.value.trim().toLowerCase();
      let visibleCount = 0;
      overlay.querySelectorAll('[data-variable]').forEach(button => {
        const variable = button.dataset.variable;
        const visible = !query || variable.includes(query) || (VARIABLE_LABELS[variable] || '').toLowerCase().includes(query);
        button.hidden = !visible;
        if (visible) visibleCount += 1;
      });
      overlay.querySelector('[data-variable-empty]').hidden = visibleCount > 0;
    });
    const editorToggle = overlay.querySelector('[data-editor-toggle]');
    editorToggle.addEventListener('click', () => {
      const isPreview = editorToggle.dataset.mode !== 'preview';
      preview.hidden = !isPreview;
      overlay.querySelector('[data-rich-editor]').closest('label').hidden = isPreview;
      editorToggle.dataset.mode = isPreview ? 'preview' : 'edit';
      editorToggle.textContent = isPreview ? 'Revenir à l’édition' : 'Aperçu';
      if (isPreview) updatePreview();
    });
    overlay.querySelectorAll('[data-command]').forEach(button => button.addEventListener('click', () => {
      editor.focus();
      document.execCommand(button.dataset.command, false, null);
      saveRange();
    }));
    overlay.querySelector('[data-format-block]').addEventListener('change', event => {
      editor.focus();
      document.execCommand('formatBlock', false, event.target.value);
      saveRange();
    });
    overlay.querySelector('[data-action="insert-link"]').addEventListener('click', () => {
      const url = window.prompt('Adresse du lien :', 'https://');
      if (!url) return;
      editor.focus();
      document.execCommand('createLink', false, url);
      saveRange();
    });
    overlay.querySelectorAll('[data-variable]').forEach(button => button.addEventListener('click', () => {
      const value = `{{${button.dataset.variable}}}`;
      if (variableTarget === subjectInput) {
        const start = subjectInput.selectionStart ?? subjectInput.value.length;
        const end = subjectInput.selectionEnd ?? start;
        subjectInput.setRangeText(value, start, end, 'end');
        subjectInput.focus();
        updatePreview();
        return;
      }
      editor.focus();
      if (savedRange) {
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(savedRange);
      }
      document.execCommand('insertText', false, value);
      saveRange();
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
    form.elements.body_html.value = overlay.querySelector('[data-rich-editor]').innerHTML;
    const data = Object.fromEntries(new FormData(form).entries());
    data.is_active = form.elements.is_active.checked;
    data.is_default = form.elements.is_default.checked;
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

  async _deleteTemplate(id) {
    const template = this.templates.find(item => item.id === id);
    if (!template || !window.confirm(`Supprimer le modèle « ${template.name} » ?`)) return;
    try {
      await deleteEmailTemplate(id);
      this.templates = this.templates.filter(item => item.id !== id);
      this._renderList();
    } catch (error) { alert(error.data?.detail || error.message || 'Erreur lors de la suppression'); }
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
