import { Table } from '../components/Table.js';
import { authStore } from '../stores/auth.js';
import { listContracts, getContract, createContract, updateContract, listProviders, listContractAttachments, uploadContractAttachment, deleteContractAttachment } from '../services/maintenanceApi.js?v=2';

const CONTRACT_TYPES = [
  { value: 'full_service', label: 'Full Service' },
  { value: 'maintenance_only', label: 'Maintenance' },
  { value: 'call_on_demand', label: 'Intervention ponctuelle' },
  { value: 'warranty', label: 'Garantie' },
  { value: 'other', label: 'Autre' },
];

function formatDate(d) { return d ? new Date(d).toLocaleDateString('fr-FR') : '-'; }
function escapeHtml(s) { return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function formatBytes(n) { if (n == null) return ''; if (n < 1024) return `${n} o`; if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`; return `${(n / (1024 * 1024)).toFixed(1)} Mo`; }

export class MaintenanceContractsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.items = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = 20;
    this.totalPages = 1;
    this.sortBy = 'subject';
    this.sortOrder = 'asc';
    this.search = '';
    this.filters = { provider_id: '', is_active: '' };
    this.table = null;
    this.providers = [];
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'reference', label: 'Référence', sortable: true },
        { key: 'subject', label: 'Objet', sortable: true },
        { key: 'provider', label: 'Prestataire', sortable: false, render: (item) => item.provider ? item.provider.name : '-' },
        { key: 'start_date', label: 'Début', sortable: true, render: (item) => formatDate(item.start_date) },
        { key: 'end_date', label: 'Fin', sortable: true, render: (item) => formatDate(item.end_date) },
        { key: 'cost', label: 'Coût annuel', sortable: false, render: (item) => item.cost ? Number(item.cost).toFixed(2) + ' €' : '-' },
        { key: 'is_active', label: 'Statut', sortable: true, render: (item) => `<span class="status-badge status-${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Actif' : 'Inactif'}</span>` },
      ],
      actions: [
        { key: 'view', label: 'Voir', icon: 'eye' },
        { key: 'edit', label: 'Modifier', icon: 'edit', disabled: (item) => !authStore.hasPermission('maintenance.manage_contracts') },
      ],
      onAction: (action, item) => this._handleAction(action, item),
      emptyMessage: 'Aucun contrat trouvé',
    });
    this._authUnsubscribe = authStore.subscribe(() => { if (this.element) this.renderTableState(); });
    await this._loadProviders();
  }

  async _loadProviders() { try { const r = await listProviders({ page_size: 1000, is_active: true }); this.providers = r.items || []; } catch (e) { this.providers = []; } }

  async loadData() {
    try {
      const params = { page: this.page, page_size: this.pageSize, sort_by: this.sortBy, sort_order: this.sortOrder };
      if (this.search) params.search = this.search;
      if (this.filters.provider_id) params.provider_id = this.filters.provider_id;
      if (this.filters.is_active !== '') params.is_active = this.filters.is_active;
      const r = await listContracts(params);
      this.items = r.items || [];
      this.total = r.total || 0;
      this.totalPages = r.total_pages || 1;
      this.renderTableState();
    } catch (e) { console.error('Erreur chargement contrats:', e); }
  }

  renderTableState() {
    if (!this.element) return;
    const countEl = this.element.querySelector('[data-count]');
    if (countEl) countEl.textContent = `${this.total} contrat${this.total > 1 ? 's' : ''}`;
    const tableContainer = this.element.querySelector('[data-table]');
    if (tableContainer) {
      this.table.setData({ items: this.items, total: this.total, page: this.page, pageSize: this.pageSize, totalPages: this.totalPages, sortBy: this.sortBy, sortOrder: this.sortOrder });
      tableContainer.innerHTML = '';
      tableContainer.appendChild(this.table.render());
    }
    const pageInfo = this.element.querySelector('[data-page-info]');
    if (pageInfo) pageInfo.textContent = `Page ${this.page} / ${this.totalPages}`;
    this.element.querySelector('[data-page="prev"]')?.setAttribute('disabled', this.page <= 1);
    this.element.querySelector('[data-page="next"]')?.setAttribute('disabled', this.page >= this.totalPages);
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content maintenance-page';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Contrats</h1>
          <p class="page-subtitle">Gestion des contrats de maintenance</p>
        </div>
        <div class="page-header-right">
          ${authStore.hasPermission('maintenance.manage_contracts') ? '<button class="btn btn-primary" data-action="create">+ Nouveau contrat</button>' : ''}
        </div>
      </div>
      <div class="page-filters">
        <input type="text" class="form-input" placeholder="Rechercher..." data-filter="search" value="${this.search}">
        <select class="form-select" data-filter="provider_id">
          <option value="">Tous les prestataires</option>
          ${this.providers.map(p => `<option value="${p.id}" ${this.filters.provider_id == p.id ? 'selected' : ''}>${p.name}</option>`).join('')}
        </select>
        <select class="form-select" data-filter="is_active">
          <option value="">Tous</option>
          <option value="true" ${this.filters.is_active === 'true' ? 'selected' : ''}>Actif</option>
          <option value="false" ${this.filters.is_active === 'false' ? 'selected' : ''}>Inactif</option>
        </select>
      </div>
      <div class="page-info"><span data-count>${this.total} contrat${this.total > 1 ? 's' : ''}</span></div>
      <div data-table></div>
      <div class="pagination">
        <button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Précédent</button>
        <span data-page-info>Page ${this.page} / ${this.totalPages}</span>
        <button class="btn btn-secondary" data-page="next" ${this.page >= this.totalPages ? 'disabled' : ''}>Suivant</button>
      </div>
    `;
    this._setupEventListeners();
    this.renderTableState();
    return this.element;
  }

  _setupEventListeners() {
    const searchInput = this.element.querySelector('[data-filter="search"]');
    let t;
    if (searchInput) searchInput.addEventListener('input', (e) => { clearTimeout(t); t = setTimeout(() => { this.search = e.target.value; this.page = 1; this.loadData(); }, 300); });
    this.element.querySelector('[data-filter="provider_id"]')?.addEventListener('change', (e) => { this.filters.provider_id = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-filter="is_active"]')?.addEventListener('change', (e) => { this.filters.is_active = e.target.value; this.page = 1; this.loadData(); });
    this.element.querySelector('[data-action="create"]')?.addEventListener('click', () => this._showFormModal(null));
    this.element.querySelector('[data-page="prev"]')?.addEventListener('click', () => { if (this.page > 1) { this.page--; this.loadData(); } });
    this.element.querySelector('[data-page="next"]')?.addEventListener('click', () => { if (this.page < this.totalPages) { this.page++; this.loadData(); } });
  }

  async _handleAction(action, item) {
    if (action === 'view' || action === 'edit') {
      try { const full = await getContract(item.id); await this._showFormModal(full); } catch (e) { alert(e.message || 'Erreur'); }
    }
  }

  async _loadAttachments(contractId, modal) {
    const list = modal?.querySelector('[data-attachments-list]');
    if (!list) return;
    const preview = modal.querySelector('[data-attachment-preview]');
    try {
      const items = (await listContractAttachments(contractId)) || [];
      const countEl = modal.querySelector('[data-attachments-count]');
      if (countEl) countEl.textContent = `(${items.length})`;
      if (!items.length) {
        list.innerHTML = '<em>Aucune pièce jointe</em>';
        if (preview) preview.innerHTML = '<em style="color:var(--color-text-secondary);">Aucun fichier à prévisualiser</em>';
        return;
      }
      const byId = new Map(items.map((a) => [String(a.id), a]));
      list.innerHTML = items.map((a) => `
        <div class="attachment-item" data-select-attachment="${a.id}" style="display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:8px;border:1px solid var(--color-border-light);border-radius:var(--radius-sm);margin-bottom:6px;">
          <span data-select-hit style="flex:1;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(a.filename)}">${escapeHtml(a.filename)}</span>
          <span style="color:var(--color-text-secondary);font-size:var(--font-size-sm);white-space:nowrap;">${formatBytes(a.file_size)}</span>
          <a class="btn btn-sm btn-secondary" href="/maintenance/attachments/${a.id}/download">Télécharger</a>
          <button type="button" class="btn btn-sm btn-danger" data-remove-attachment="${a.id}">Supprimer</button>
        </div>`).join('');
      list.querySelectorAll('[data-select-attachment]').forEach((el) => {
        el.addEventListener('click', (e) => {
          if (e.target.closest('a,button')) return;
          this._renderAttachmentPreview(preview, byId.get(el.dataset.selectAttachment));
        });
      });
      list.querySelectorAll('[data-remove-attachment]').forEach((btn) => {
        btn.addEventListener('click', async () => {
          if (!confirm('Supprimer cette pièce jointe ?')) return;
          try {
            await deleteContractAttachment(btn.dataset.removeAttachment);
            this._loadAttachments(contractId, modal);
          } catch (err) { alert(err.message || 'Erreur lors de la suppression'); }
        });
      });
      this._renderAttachmentPreview(preview, items[0]);
    } catch (e) {
      list.innerHTML = '<em>Impossible de charger les pièces jointes</em>';
    }
  }

  _renderAttachmentPreview(container, attachment) {
    if (!container) return;
    if (!attachment) {
      container.innerHTML = '<em style="color:var(--color-text-secondary);">Sélectionnez un fichier pour l\'aperçu</em>';
      return;
    }
    const url = `/maintenance/attachments/${attachment.id}/download`;
    const mime = attachment.mime_type || '';
    if (mime === 'application/pdf') {
      container.innerHTML = `<iframe title="Aperçu de ${escapeHtml(attachment.filename)}" sandbox src="${url}" style="display:block;width:100%;height:420px;border:0;background:#fff;"></iframe>`;
    } else if (mime.startsWith('image/') && mime !== 'image/svg+xml') {
      container.innerHTML = `<img src="${url}" alt="${escapeHtml(attachment.filename)}" style="max-width:100%;max-height:420px;display:block;margin:0 auto;">`;
    } else {
      container.innerHTML = `
        <div style="text-align:center;padding:24px;">
          <p style="margin:0 0 4px;"><strong>${escapeHtml(attachment.filename)}</strong></p>
          <p style="margin:0 0 4px;color:var(--color-text-secondary);font-size:var(--font-size-sm);">${mime ? escapeHtml(mime) : 'Type inconnu'} — ${formatBytes(attachment.file_size)}</p>
          <p style="margin:0 0 12px;color:var(--color-text-secondary);">Aperçu non disponible pour ce type de fichier.</p>
          <a class="btn btn-primary" href="${url}">Télécharger</a>
        </div>`;
    }
  }

  async _showFormModal(contract) {
    const isEdit = !!contract;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';

    // Build modal HTML using string concatenation to avoid nested template literals
    const tabButtons = isEdit
      ? `<div class="buildings-tabs" role="tablist">
           <button type="button" role="tab" class="tab-button tab-button--active" data-tab="infos" aria-selected="true" aria-controls="panel-infos">Informations</button>
           <button type="button" role="tab" class="tab-button" data-tab="attachments" aria-selected="false" aria-controls="panel-attachments">Pièces jointes <span data-attachments-count>(0)</span></button>
         </div>`
      : '';

    const infosPanel = isEdit ? `
          <div data-tab-panel="infos" role="tabpanel" id="panel-infos" hidden>
            <form data-form>
              <div class="form-row">
                <label><span>Objet *</span><input name="subject" value="${isEdit ? (contract.subject || '') : ''}" required maxlength="300"></label>
                <label><span>Référence *</span><input name="reference" value="${isEdit ? (contract.reference || '') : ''}" required maxlength="100"></label>
              </div>
              <div class="form-row">
                <label><span>Type *</span><select name="contract_type" required>
                  ${CONTRACT_TYPES.map(t => `<option value="${t.value}" ${isEdit && contract.contract_type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}
                </select></label>
                <label><span>Prestataire *</span><select name="provider_id" required>
                  <option value="">-- Sélectionner --</option>
                  ${this.providers.map(p => `<option value="${p.id}" ${isEdit && contract.provider_id == p.id ? 'selected' : ''}>${p.name}</option>`).join('')}
                </select></label>
              </div>
              <div class="form-row">
                <label><span>Date début *</span><input type="date" name="start_date" value="${isEdit && contract.start_date ? contract.start_date : ''}" required></label>
                <label><span>Date fin</span><input type="date" name="end_date" value="${isEdit && contract.end_date ? contract.end_date : ''}"></label>
              </div>
              <div class="form-row">
                <label><span>Coût annuel</span><input type="number" name="annual_cost" step="0.01" min="0" value="${isEdit && contract.cost ? contract.cost : ''}"></label>
                <label><span>Renouvellement auto</span><input type="checkbox" name="auto_renew" ${isEdit && contract.auto_renew ? 'checked' : ''}></label>
              </div>
              <div class="form-row">
                <label><span>Description</span><textarea name="description" rows="3">${isEdit ? (contract.description || '') : ''}</textarea></label>
              </div>
              <div class="form-row">
                <label><span>Actif</span><input type="checkbox" name="is_active" ${isEdit ? (contract.is_active ? 'checked' : '') : 'checked'}></label>
              </div>
            </form>
          </div>` : '';

    const attachmentsPanel = isEdit ? `
          <div data-tab-panel="attachments" role="tabpanel" id="panel-attachments" hidden>
            <div class="attachments-layout">
              <div class="attachments-list-col">
                <div data-attachments-list><em>Chargement…</em></div>
                <input type="file" data-attachments-input multiple>
                <div data-attachment-preview style="margin-top:12px;border:1px solid var(--color-border-light);border-radius:var(--radius-sm);min-height:200px;display:flex;align-items:center;justify-content:center;background:var(--color-bg-secondary);overflow:auto;"><em style="color:var(--color-text-secondary);">Sélectionnez un fichier</em></div>
              </div>
              <div class="attachments-actions-col">
                <button type="button" class="btn btn-sm btn-secondary" data-action="close-attachments">Fermer</button>
              </div>
            </div>
          </div>` : '';

    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${isEdit ? 'Modifier le contrat' : 'Nouveau contrat'}</h2>
            <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            ${tabButtons}
            <form data-form>
              <div class="form-row">
                <label><span>Objet *</span><input name="subject" value="${isEdit ? (contract.subject || '') : ''}" required maxlength="300"></label>
                <label><span>Référence *</span><input name="reference" value="${isEdit ? (contract.reference || '') : ''}" required maxlength="100"></label>
              </div>
              <div class="form-row">
                <label><span>Type *</span><select name="contract_type" required>
                  ${CONTRACT_TYPES.map(t => `<option value="${t.value}" ${isEdit && contract.contract_type === t.value ? 'selected' : ''}>${t.label}</option>`).join('')}
                </select></label>
                <label><span>Prestataire *</span><select name="provider_id" required>
                  <option value="">-- Sélectionner --</option>
                  ${this.providers.map(p => `<option value="${p.id}" ${isEdit && contract.provider_id == p.id ? 'selected' : ''}>${p.name}</option>`).join('')}
                </select></label>
              </div>
              <div class="form-row">
                <label><span>Date début *</span><input type="date" name="start_date" value="${isEdit && contract.start_date ? contract.start_date : ''}" required></label>
                <label><span>Date fin</span><input type="date" name="end_date" value="${isEdit && contract.end_date ? contract.end_date : ''}"></label>
              </div>
              <div class="form-row">
                <label><span>Coût annuel</span><input type="number" name="annual_cost" step="0.01" min="0" value="${isEdit && contract.cost ? contract.cost : ''}"></label>
                <label><span>Renouvellement auto</span><input type="checkbox" name="auto_renew" ${isEdit && contract.auto_renew ? 'checked' : ''}></label>
              </div>
              <div class="form-row">
                <label><span>Description</span><textarea name="description" rows="3">${isEdit ? (contract.description || '') : ''}</textarea></label>
              </div>
              <div class="form-row">
                <label><span>Actif</span><input type="checkbox" name="is_active" ${isEdit ? (contract.is_active ? 'checked' : '') : 'checked'}></label>
              </div>
            </form>
            ${infosPanel}
            ${attachmentsPanel}
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Annuler</button>
            <button class="btn btn-primary" data-action="save">${isEdit ? 'Enregistrer' : 'Créer'}</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    // Écouteur pour le input file (pièces jointes)
    if (isEdit) {
      this._loadAttachments(contract.id, modal);
      const fileInput = modal.querySelector('[data-attachments-input]');
      if (fileInput) {
        fileInput.addEventListener('change', async (e) => {
          const files = Array.from(e.target.files || []);
          for (const f of files) {
            try { await uploadContractAttachment(contract.id, f); }
            catch (err) { alert(err.message || `Échec de l'envoi de ${f.name}`); }
          }
          e.target.value = '';
          this._loadAttachments(contract.id, modal);
        });
      }
    }
    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    // Gestion des onglets
    if (isEdit) {
      modal.querySelectorAll('[data-tab-btn]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const tab = btn.dataset.tab;
          modal.querySelectorAll('[data-tab-btn]').forEach((b) => {
            b.classList.toggle('tab-button--active', b.dataset.tab === tab);
            b.setAttribute('aria-selected', b.dataset.tab === tab);
          });
          modal.querySelectorAll('[data-tab-panel]').forEach((p) => {
            p.hidden = p.dataset.tabPanel !== tab;
          });
          if (tab === 'attachments') {
            this._loadAttachments(contract.id, modal);
          }
        });
      });
    }
    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const fd = new FormData(modal.querySelector('[data-form]'));
      const data = {};
      for (const [k, v] of fd.entries()) {
        if (k === 'is_active' || k === 'auto_renew') { data[k] = true; continue; }
        if (v === '') continue;
        if (k === 'provider_id') data[k] = parseInt(v, 10);
        else if (k === 'annual_cost') data.cost = parseFloat(v);
        else data[k] = v;
      }
      if (!data.subject || !data.reference || !data.provider_id || !data.start_date) { alert('Les champs Objet, Référence, Prestataire et Date début sont obligatoires'); return; }
      try {
        if (isEdit) {
          await updateContract(contract.id, data);
          modal.remove();
          this.loadData();
        } else {
          const created = await createContract(data);
          modal.remove();
          this.loadData();
          try {
            const full = await getContract(created.id);
            await this._showFormModal(full);
          } catch (e) { /* contrat créé, ouverture du modal en mode édition ignorée silencieusement */ }
        }
      } catch (e) { alert(e.message || 'Erreur lors de la sauvegarde'); }
    });
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createMaintenanceContractsPage(router) { return new MaintenanceContractsPage(router); }
