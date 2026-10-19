import { Table } from '../components/Table.js';
import { listExpenses, listSites, listAccountCodes, listAliases, assignSites, analyzeImport, validateImport } from '../services/intendanceApi.js';

export class IntendanceExpensesPage {
  constructor() {
    this.element = null; this.items = []; this.sites = []; this.accountCodes = []; this.aliases = []; this.search = ''; this.missing = ''; this.activeTab = 'details'; this.importState = null;
    this.table = new Table({
      columns: [
        { key: 'expense_date', label: 'Date', sortable: true }, { key: 'req_number', label: 'Demande', sortable: true },
        { key: 'item_description', label: 'Dépense' }, { key: 'amount', label: 'Montant', render: item => `${item.amount} €` },
        { key: 'account_code', label: 'Code comptable', render: item => item.account_code || '<span class="status-badge inactive">Non résolu</span>' },
        { key: 'category', label: 'Catégorie', render: item => item.category || '<span class="status-badge inactive">À affecter</span>' },
        { key: 'user_name', label: 'Utilisateur', render: item => item.user_name || '<span class="status-badge inactive">À identifier</span>' },
        { key: 'site.name', label: 'Site', render: item => item.site?.name || '<span class="status-badge inactive">À affecter</span>' },
      ], emptyMessage: 'Aucune dépense importée',
    });
  }
  async load() { const [data, sites] = await Promise.all([listExpenses({ page_size: 100, search: this.search, missing: this.missing }), listSites()]); this.items = data.items || []; this.sites = sites.items || []; this.table.setData({ items: this.items, total: data.total, page: data.page, pageSize: data.page_size, totalPages: data.total_pages }); this._renderTable(); }
  async loadReferences() { const [codes, aliases, sites] = await Promise.all([listAccountCodes(), listAliases(), listSites()]); this.accountCodes = codes.items || []; this.aliases = aliases.items || []; this.sites = sites.items || []; this._renderTabContent(); }
  render() {
    if (!this.element) this.element = document.createElement('div'); this.element.className = 'page-content intendance-expenses-page';
    this.element.innerHTML = `<div class="page-header"><div class="page-header-left"><h1>Suivi des dépenses</h1><p class="page-subtitle">Import, contrôle et affectation des dépenses de l’Intendance.</p></div><div class="page-header-right"><label class="btn btn-primary"><input data-import type="file" accept=".xlsx" hidden>Importer Excel</label></div></div><nav class="page-tabs" role="tablist">${[['details','Détails'],['references','Référentiels'],['users','Utilisateurs'],['sites','Sites']].map(([key,label]) => `<button class="page-tab ${this.activeTab === key ? 'active' : ''}" data-tab="${key}" type="button">${label}</button>`).join('')}</nav><div data-tab-content></div><div class="import-progress" data-progress hidden></div>`;
    this._bind(); this._renderTabContent(); return this.element;
  }
  _bind() {
    this.element.querySelectorAll('[data-tab]').forEach(button => button.onclick = async () => { this.activeTab = button.dataset.tab; if (this.activeTab !== 'details') await this.loadReferences(); else this._renderTabContent(); });
    this.element.querySelector('[data-import]').onchange = e => this._runImport(e.target.files[0]);
  }
  async _runImport(file) {
    if (!file) return; this.importState = { step: 1, status: 'Téléversement du fichier…' }; this._renderProgress();
    try { this.importState = { step: 2, status: 'Analyse du classeur et recherche des doublons…' }; this._renderProgress(); const batch = await analyzeImport(file); this.importState = { step: 3, status: 'Prévisualisation terminée', batch }; this._renderProgress(); await new Promise(resolve => setTimeout(resolve, 250)); this.importState = { ...this.importState, step: 4, status: 'Validation et enregistrement…' }; this._renderProgress(); const result = await validateImport(batch.id); this.importState = { step: 5, status: 'Import terminé', result, batch }; this._renderProgress(); await this.load(); } catch (error) { this.importState = { step: 0, status: error.message || 'Échec de l’import', error: true }; this._renderProgress(); }
  }
  _renderProgress() { const target = this.element?.querySelector('[data-progress]'); if (!target || !this.importState) return; target.hidden = false; const s = this.importState; const bilan = s.batch?.bilan; target.innerHTML = `<strong>${s.status}</strong><div class="import-progress-bar"><span style="width:${Math.max(5, s.step * 20)}%"></span></div>${bilan ? `<div class="import-summary"><span>${bilan.rows_total} lignes analysées</span><span>${bilan.rows_new} nouvelles</span><span>${bilan.rows_duplicate_existing + bilan.rows_duplicate_in_file} doublons</span><span>${bilan.rows_invalid} invalides</span></div>` : ''}${s.result ? `<p>${s.result.created_count} dépense(s) enregistrée(s).</p>` : ''}`; }
  _renderTabContent() {
    if (!this.element) return; const target = this.element.querySelector('[data-tab-content]'); if (!target) return;
    if (this.activeTab === 'details') { target.innerHTML = `<div class="page-filters"><div class="filter-group"><label class="sr-only" for="expense-search">Rechercher</label><input id="expense-search" class="form-input" data-search placeholder="Rechercher une dépense…" value="${this.search}"></div><div class="filter-group"><select class="form-select" data-missing><option value="">Toutes les dépenses</option><option value="site">Site à affecter</option><option value="category">Catégorie à affecter</option><option value="user">Utilisateur à identifier</option></select></div><button class="btn btn-secondary" data-refresh>Actualiser</button></div><div class="page-actions"><select class="form-select" data-site><option value="">Affecter le site sélectionné…</option></select><button class="btn btn-secondary" data-bulk>Affecter</button></div><div data-table></div>`; this._bindDetails(); this._renderTable(); return; }
    const rows = this.activeTab === 'references' ? this.accountCodes.map(x => `<tr><td>${x.code}</td><td>${x.label || '—'}</td><td>${x.category || 'Non résolue'}</td></tr>`).join('') : this.activeTab === 'users' ? this.aliases.map(x => `<tr><td>${x.alias}</td><td>${x.user_name}</td></tr>`).join('') : this.sites.map(x => `<tr><td>${x.name}</td><td>${x.is_active ? 'Actif' : 'Inactif'}</td></tr>`).join(''); const head = this.activeTab === 'references' ? '<th>Code</th><th>Libellé</th><th>Catégorie</th>' : this.activeTab === 'users' ? '<th>Alias carte</th><th>Utilisateur</th>' : '<th>Site</th><th>Statut</th>'; target.innerHTML = `<div class="table-container"><table class="users-table"><thead><tr>${head}</tr></thead><tbody>${rows || '<tr><td colspan="3">Aucune donnée</td></tr>'}</tbody></table></div>`;
  }
  _bindDetails() { this.element.querySelector('[data-refresh]').onclick = () => this.load(); this.element.querySelector('[data-search]').onchange = e => { this.search = e.target.value; this.load(); }; this.element.querySelector('[data-missing]').onchange = e => { this.missing = e.target.value; this.load(); }; this.element.querySelector('[data-bulk]').onclick = async () => { const siteId = Number(this.element.querySelector('[data-site]').value); const ids = [...this.element.querySelectorAll('[data-expense-id]:checked')].map(input => Number(input.dataset.expenseId)); if (siteId && ids.length) { await assignSites(ids, siteId); await this.load(); } };
  }
  _renderTable() { if (!this.element) return; const site = this.element.querySelector('[data-site]'); if (site) site.innerHTML = '<option value="">Affecter le site sélectionné…</option>' + this.sites.map(item => `<option value="${item.id}">${item.name}</option>`).join(''); const container = this.element.querySelector('[data-table]'); if (!container) return; container.innerHTML = ''; const tableElement = this.table.render(); container.appendChild(tableElement); tableElement.querySelector('thead tr').insertAdjacentHTML('afterbegin', '<th></th>'); tableElement.querySelectorAll('tbody tr[data-id]').forEach(row => row.insertAdjacentHTML('afterbegin', `<td><input type="checkbox" data-expense-id="${row.dataset.id}" aria-label="Sélectionner la dépense"></td>`)); }
}
export const createIntendanceExpensesPage = () => new IntendanceExpensesPage();
