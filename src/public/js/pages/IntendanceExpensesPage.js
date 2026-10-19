import { Table } from '../components/Table.js';
import { listExpenses, listSites, assignSites, analyzeImport, validateImport } from '../services/intendanceApi.js';

export class IntendanceExpensesPage {
  constructor() {
    this.element = null; this.items = []; this.sites = []; this.search = ''; this.missing = '';
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
  render() {
    if (!this.element) this.element = document.createElement('div'); this.element.className = 'page-content intendance-expenses-page';
    this.element.innerHTML = `<div class="page-header"><div class="page-header-left"><h1>Suivi des dépenses</h1><p class="page-subtitle">Import, contrôle et affectation des dépenses de l’Intendance.</p></div><div class="page-header-right"><label class="btn btn-primary"><input data-import type="file" accept=".xlsx" hidden>Importer Excel</label></div></div><nav class="page-tabs" role="tablist"><button class="page-tab active" type="button">Détails</button><button class="page-tab" type="button" disabled>Référentiels</button><button class="page-tab" type="button" disabled>Utilisateurs</button><button class="page-tab" type="button" disabled>Sites</button></nav><div class="page-filters"><div class="filter-group"><label class="sr-only" for="expense-search">Rechercher</label><input id="expense-search" class="form-input" data-search placeholder="Rechercher une dépense…" value="${this.search}"></div><div class="filter-group"><label class="sr-only" for="expense-missing">Filtrer les champs incomplets</label><select id="expense-missing" class="form-select" data-missing><option value="">Toutes les dépenses</option><option value="site">Site à affecter</option><option value="category">Catégorie à affecter</option><option value="user">Utilisateur à identifier</option></select></div><button class="btn btn-secondary" data-refresh>Actualiser</button></div><div class="page-actions"><select class="form-select" data-site><option value="">Affecter le site sélectionné…</option></select><button class="btn btn-secondary" data-bulk>Affecter</button></div><div data-table></div>`;
    this._bind(); this._renderTable(); return this.element;
  }
  _bind() {
    this.element.querySelector('[data-refresh]').onclick = () => this.load(); this.element.querySelector('[data-search]').onchange = e => { this.search = e.target.value; this.load(); }; this.element.querySelector('[data-missing]').onchange = e => { this.missing = e.target.value; this.load(); };
    this.element.querySelector('[data-bulk]').onclick = async () => { const siteId = Number(this.element.querySelector('[data-site]').value); const ids = [...this.element.querySelectorAll('[data-expense-id]:checked')].map(input => Number(input.dataset.expenseId)); if (siteId && ids.length) { await assignSites(ids, siteId); await this.load(); } };
    this.element.querySelector('[data-import]').onchange = async e => { const file = e.target.files[0]; if (!file) return; const batch = await analyzeImport(file); const result = await validateImport(batch.id); window.alert(`${result.created_count} dépense(s) importée(s).`); await this.load(); };
  }
  _renderTable() { if (!this.element) return; const site = this.element.querySelector('[data-site]'); if (site) site.innerHTML = '<option value="">Affecter le site sélectionné…</option>' + this.sites.map(item => `<option value="${item.id}">${item.name}</option>`).join(''); const container = this.element.querySelector('[data-table]'); if (!container) return; container.innerHTML = ''; const tableElement = this.table.render(); container.appendChild(tableElement); tableElement.querySelector('thead tr').insertAdjacentHTML('afterbegin', '<th></th>'); tableElement.querySelectorAll('tbody tr[data-id]').forEach(row => row.insertAdjacentHTML('afterbegin', `<td><input type="checkbox" data-expense-id="${row.dataset.id}" aria-label="Sélectionner la dépense"></td>`)); }
}
export const createIntendanceExpensesPage = () => new IntendanceExpensesPage();
