import { listExpenses, listSites, assignSites, analyzeImport, validateImport } from '../services/intendanceApi.js';

export class IntendanceExpensesPage {
  constructor() { this.element = null; this.items = []; this.sites = []; }
  async load() { const [expenses, sites] = await Promise.all([listExpenses({ page_size: 100 }), listSites()]); this.items = expenses.items || []; this.sites = sites.items || []; this.renderRows(); }
  render() {
    this.element = document.createElement('section'); this.element.className = 'page intendance-expenses';
    this.element.innerHTML = `<div class="page-header"><h1>Suivi des dépenses</h1><label class="button"><input type="file" accept=".xlsx" hidden>Importer un fichier Excel</label></div><div class="tabs"><button class="active">Détails</button><button>Référentiels</button><button>Utilisateurs</button><button>Sites</button></div><div class="toolbar"><button data-bulk>Affecter le site sélectionné</button><select data-site><option value="">Site…</option></select></div><div class="table-container"><table><thead><tr><th></th><th>Date</th><th>Demande</th><th>Libellé</th><th>Montant</th><th>Code</th><th>Catégorie</th><th>Utilisateur</th><th>Site</th></tr></thead><tbody></tbody></table></div>`;
    const input = this.element.querySelector('input[type=file]'); input.addEventListener('change', async () => { if (!input.files[0]) return; const batch = await analyzeImport(input.files[0]); const result = await validateImport(batch.id); alert(`${result.created_count} dépense(s) importée(s)`); await this.load(); });
    this.element.querySelector('[data-bulk]').addEventListener('click', async () => { const site_id = Number(this.element.querySelector('[data-site]').value); const ids = [...this.element.querySelectorAll('input[data-id]:checked')].map(x => Number(x.dataset.id)); if (site_id && ids.length) { await assignSites(ids, site_id); await this.load(); } });
    this.renderRows(); return this.element;
  }
  renderRows() { if (!this.element) return; const select = this.element.querySelector('[data-site]'); if (select) select.innerHTML = '<option value="">Site…</option>' + this.sites.map(s => `<option value="${s.id}">${s.name}</option>`).join(''); const body = this.element.querySelector('tbody'); if (body) body.innerHTML = this.items.map(x => `<tr><td><input type="checkbox" data-id="${x.id}"></td><td>${x.expense_date || '—'}</td><td>${x.req_number}</td><td>${x.item_description || '—'}</td><td>${x.amount}</td><td>${x.account_code || 'Non résolu'}</td><td>${x.category || 'À affecter'}</td><td>${x.user_name || 'À identifier'}</td><td>${x.site?.name || 'À affecter'}</td></tr>`).join(''); }
}

export const createIntendanceExpensesPage = () => new IntendanceExpensesPage();
