import { authStore } from '../stores/auth.js';
import { getExpenseDashboard, getMealCostBySite, listExpenses, listAliases, listSites } from '../services/intendanceApi.js';
import { Table } from '../components/Table.js';

const CATEGORY_COLORS = {
  'matriel': '#4F46E5',
  'repair': '#10B981',
  'service': '#F59E0B',
  'autre': '#6B7280',
};

function getCategoryColor(category) {
  return CATEGORY_COLORS[category] || '#6B7280';
}

export class IntendanceDashboardPage {
  constructor(options = {}) {
    this.onEditExpense = options.onEditExpense;
    this.onDeleteExpense = options.onDeleteExpense;
    this.filterStorageKey = 'forgeai:intendance-dashboard-filters';
    this.element = null;
    this.categories = [];
    this.amounts = [];
    this.maxAmount = 0;
    this.dashboard = { kpis: {}, categories: [], monthly: [], daily: [], users: [], sites: [], top_expenses: [] };
    this.mealSiteCosts = [];
    this.mealSiteCostsUnavailable = false;
    this.expenses = [];
    this.filterDateFrom = '';
    this.filterDateTo = '';
    this.filterUser = [];
    this.filterSite = [];
    this.filterCategory = [];
    this.activeView = 'general';
    this.expenseSearch = '';
    this.expensePage = 1;
    this.expenseSortBy = 'expense_date';
    this.expenseSortOrder = 'desc';
    this.expenseListMeta = { total: 0, total_pages: 1, page_size: 20 };
    this.expenseTable = new Table({
      columns: [
        { key: 'expense_date', label: 'Date', sortable: true },
        { key: 'req_number', label: 'Demande', sortable: true },
        { key: 'item_description', label: 'Libellé', sortable: true },
        { key: 'category', label: 'Catégorie', sortable: true, render: item => item.category || 'Non classée' },
        { key: 'user_name', label: 'Utilisateur', sortable: true },
        { key: 'site.name', label: 'Site', sortable: true },
        { key: 'amount', label: 'Montant', sortable: true, render: item => this._money(item.amount) },
      ],
      actions: [{ key: 'edit', label: 'Modifier', icon: 'edit' }, { key: 'delete', label: 'Supprimer', icon: 'trash' }],
      onAction: (action, item) => action === 'edit' ? this.onEditExpense?.(item) : this.onDeleteExpense?.(item),
      onSort: (column, order) => { this.expenseSortBy = column; this.expenseSortOrder = order; this.expensePage = 1; this.loadDashboard(); },
      emptyMessage: 'Aucune dépense pour les filtres sélectionnés',
    });
    this._loadFilterState();
    this.page = 1;
    this.refreshTimer = null;
  }

  async init() {
    await this.loadDashboard();
    clearInterval(this.refreshTimer);
    this.refreshTimer = setInterval(() => this.loadDashboard(), 30000);
  }

  async loadDashboard() {
    const params = new URLSearchParams();
    const today = new Date();
    const effectiveDateFrom = this.filterDateFrom || `${today.getFullYear()}-01-01`;
    const effectiveDateTo = this.filterDateTo || today.toISOString().split('T')[0];
    params.append('expense_date_from', effectiveDateFrom);
    params.append('expense_date_to', effectiveDateTo);
    this.filterUser.forEach(user => params.append('user_name', user));
    this.filterSite.forEach(site => params.append('site_id', site));
    const viewCategory = this.activeView === 'meals' ? 'Nourriture' : this.activeView === 'energy' ? 'Energie' : null;
    (viewCategory ? [viewCategory] : this.filterCategory).forEach(category => params.append('category', category));

    const mealCostsPromise = this.activeView === 'meals'
      ? getMealCostBySite(params).then(result => ({ result, unavailable: false })).catch(() => ({ result: null, unavailable: true }))
      : Promise.resolve({ result: null, unavailable: false });
    const [dashboard, expenseList, mealCosts] = await Promise.all([
      getExpenseDashboard(params),
      listExpenses(new URLSearchParams([...params.entries(), ['dashboard', 'true'], ['search', this.expenseSearch], ['page', String(this.expensePage)], ['page_size', '20'], ['sort_by', this.expenseSortBy], ['sort_order', this.expenseSortOrder]])),
      mealCostsPromise,
    ]);
    this.mealSiteCosts = mealCosts.result?.items || [];
    this.mealSiteCostsUnavailable = mealCosts.unavailable;
    this.dashboard = dashboard || this.dashboard;
    this.expenses = expenseList?.items || [];
    this.expenseListMeta = expenseList || this.expenseListMeta;
    const categories = this.dashboard.categories || [];
    this.categories = categories.map(item => item.name);
    this.amounts = categories.map(item => Number(item.amount) || 0);
    this.maxAmount = Math.max(...this.amounts, 1);

    this.render();
  }

  _loadFilterState() {
    try {
      const saved = JSON.parse(localStorage.getItem(this.filterStorageKey) || '{}');
      this.filterDateFrom = typeof saved.dateFrom === 'string' ? saved.dateFrom : '';
      this.filterDateTo = typeof saved.dateTo === 'string' ? saved.dateTo : '';
      this.filterUser = Array.isArray(saved.users) ? saved.users : [];
      this.filterSite = Array.isArray(saved.sites) ? saved.sites.map(Number).filter(Number.isFinite) : [];
      this.filterCategory = Array.isArray(saved.categories) ? saved.categories : [];
    } catch { /* stockage indisponible ou contenu invalide */ }
  }

  _saveFilterState() {
    try { localStorage.setItem(this.filterStorageKey, JSON.stringify({ dateFrom: this.filterDateFrom, dateTo: this.filterDateTo, users: this.filterUser, sites: this.filterSite, categories: this.filterCategory })); } catch { /* stockage indisponible */ }
  }

  render() {
    if (!this.element) this.element = document.createElement('div');
    this.element.className = 'page-content intendance-dashboard-page';
    
    // Date filter
    const today = new Date();
    const firstOfYear = new Date(today.getFullYear(), 0, 1);
    const dateFrom = this.filterDateFrom ? new Date(this.filterDateFrom) : firstOfYear;
    const dateTo = this.filterDateTo ? new Date(this.filterDateTo) : today;
    
    const dateFromStr = dateFrom.toISOString().split('T')[0];
    const dateToStr = dateTo.toISOString().split('T')[0];
    const rangeStart = new Date('2020-01-01');
    const dayValue = date => Math.round((date - rangeStart) / 86400000);
    const dateFromValue = dayValue(dateFrom);
    const dateToValue = this.filterDateTo ? dayValue(dateTo) : dayValue(dateTo);
    const rangeMax = dayValue(today);

    const generalView = this.activeView === 'general';
    const filterMarkup = `
        <!-- Filtres -->
        <div class="dashboard-filters">
          <div class="dashboard-filters-row dashboard-filters-row--top">
          <div class="filter-group">
            <label class="filter-label">Période</label>
            <div class="slider-wrapper">
              <div class="date-range-values"><input type="date" class="form-input" data-date-input="from" value="${dateFromStr}" aria-label="Date de début"><span>–</span><input type="date" class="form-input" data-date-input="to" value="${dateToStr}" aria-label="Date de fin"></div>
              <div class="date-range-sliders"><input type="range" id="date-from" min="0" max="${rangeMax}" value="${dateFromValue}" aria-label="Date de début"><input type="range" id="date-to" min="0" max="${rangeMax}" value="${dateToValue}" aria-label="Date de fin"></div>
            </div>
          </div>
          </div>
          <div class="dashboard-filters-row dashboard-filters-row--bottom">
          ${generalView ? this._renderMultiFilter('category', 'Catégorie', (this.dashboard.categories || []).map(item => item.name), this.filterCategory) : ''}
          ${this._renderMultiFilter('user', 'Utilisateur', [], this.filterUser)}
          ${this._renderMultiFilter('site', 'Site', [], this.filterSite)}
          <button type="button" class="btn btn-secondary" data-reset-filters>Réinitialiser</button>
          </div>
        </div>`;
    this.element.innerHTML = `
      <div class="dashboard-container">
        <div class="admin-tabs intendance-dashboard-tabs" role="tablist" aria-label="Vues du tableau de bord"><button role="tab" class="admin-tab" data-dashboard-view="general" aria-selected="${generalView}" type="button">Général</button><button role="tab" class="admin-tab" data-dashboard-view="meals" aria-selected="${this.activeView === 'meals'}" type="button">Repas</button><button role="tab" class="admin-tab" data-dashboard-view="energy" aria-selected="${this.activeView === 'energy'}" type="button">Énergie</button></div>
        ${filterMarkup}

        <div class="intendance-kpi-grid">${this._renderKpis()}</div>
        <div class="intendance-dashboard-grid">
          ${generalView ? '<section class="histogram-container chart-card"><div class="chart-heading"><div><h2>Répartition par catégorie</h2><p>Cliquer sur une catégorie pour filtrer</p></div><div class="chart-legend"><span class="chart-legend-item"><i class="chart-swatch chart-swatch--category"></i>Part du total</span></div></div>' + this._renderCategoryBars() + '</section>' : ''}
          <section class="histogram-container chart-card"><div class="chart-heading"><div><h2>Répartition par utilisateur</h2><p>Montant attribué et nombre de dépenses</p></div><div class="chart-legend"><span class="chart-legend-item"><i class="chart-swatch chart-swatch--user"></i>Montant (€)</span></div></div>${this._renderUserBars()}</section>
          <section class="histogram-container chart-card"><div class="chart-heading"><div><h2>${this.activeView === 'energy' ? 'Coût de l’énergie par site' : 'Répartition par site'}</h2><p>Montant total et nombre de dépenses</p></div><div class="chart-legend"><span class="chart-legend-item"><i class="chart-swatch chart-swatch--user"></i>Montant (€)</span></div></div>${this._renderSiteBars()}</section>
          ${this.activeView === 'meals' ? `<section class="histogram-container chart-card chart-card--monthly"><div class="chart-heading"><div><h2>Coût du repas par personne et par site</h2><p>Dépenses de nourriture divisées par les repas déclarés dans Agenda (jours ouvrés) et les jours d'occupation du module Hébergement (7j/7)</p></div><div class="chart-legend"><span class="chart-legend-item"><i class="chart-swatch chart-swatch--category"></i>Coût par repas (€)</span></div></div>${this._renderMealCostBySite()}</section>` : ''}
          <section class="histogram-container chart-card chart-card--monthly"><div class="chart-heading"><div><h2>${this.activeView === 'meals' ? 'Évolution des dépenses de nourriture' : this.activeView === 'energy' ? 'Évolution des dépenses d’énergie' : 'Évolution mensuelle'}</h2></div><div class="chart-legend">${this._renderMonthlyLegend()}</div></div><canvas id="monthly-chart" aria-label="Évolution mensuelle des dépenses par catégorie"></canvas></section>
        </div>
        <section class="histogram-container intendance-expense-list"><div class="chart-heading"><div><h2>Dépenses filtrées</h2><p>${this.expenseListMeta.total || 0} dépense(s) correspondant aux filtres</p></div></div>${this._renderExpenseList()}</section>

      </div>
    `;

    this._bind();
    this.element.querySelectorAll('[data-dashboard-view]').forEach(button => button.onclick = () => { this.activeView = button.dataset.dashboardView; this.expensePage = 1; this.loadDashboard(); });
    this._renderExpenseTable(); this._renderHistogram(); this._loadUsersSites();
    return this.element;
  }

  _renderExpenseTable() {
    const target = this.element.querySelector('[data-expense-table]');
    if (!target) return;
    this.expenseTable.setData({ items: this.expenses, total: this.expenseListMeta.total || 0, page: this.expenseListMeta.page || this.expensePage, pageSize: 20, totalPages: this.expenseListMeta.total_pages || 1, sortBy: this.expenseSortBy, sortOrder: this.expenseSortOrder });
    target.replaceChildren(this.expenseTable.render());
    const totalPages = this.expenseListMeta.total_pages || 1;
    const pager = document.createElement('div');
    pager.className = 'users-pagination';
    pager.innerHTML = `<div class="pagination-info">Page <strong>${this.expensePage}</strong> sur <strong>${totalPages}</strong> (${this.expenseListMeta.total || 0} total)</div><div class="pagination-controls"><button class="btn btn-sm btn-secondary" data-page-prev ${this.expensePage <= 1 ? 'disabled' : ''}>‹ Précédent</button><button class="btn btn-sm btn-secondary" data-page-next ${this.expensePage >= totalPages ? 'disabled' : ''}>Suivant ›</button></div>`;
    target.appendChild(pager);
    pager.querySelector('[data-page-prev]').onclick = () => { if (this.expensePage > 1) { this.expensePage -= 1; this.loadDashboard(); } };
    pager.querySelector('[data-page-next]').onclick = () => { if (this.expensePage < totalPages) { this.expensePage += 1; this.loadDashboard(); } };
  }

  _bind() {
    const dashboard = this;
    
    // Date filter
    this.element.querySelectorAll('#date-from, #date-to').forEach(input => {
      input.oninput = () => {
        this._updateDateRangeTrack();
      };
      input.onchange = () => {
        const start = new Date('2020-01-01');
        const toDate = value => new Date(start.getTime() + Number(value) * 86400000).toISOString().split('T')[0];
        const fromValue = Number(this.element.querySelector('#date-from').value);
        const toValue = Number(this.element.querySelector('#date-to').value);
        this.filterDateFrom = toDate(Math.min(fromValue, toValue));
        this.filterDateTo = toDate(Math.max(fromValue, toValue));
        this._saveFilterState();
        this._updateDateRangeTrack();
        this.element.querySelector('[data-date-input="from"]').value = this.filterDateFrom;
        this.element.querySelector('[data-date-input="to"]').value = this.filterDateTo;
        this.loadDashboard();
      };
    });
    const rangeTrack = this.element.querySelector('.date-range-sliders');
    rangeTrack?.addEventListener('click', event => {
      if (event.target !== rangeTrack) return;
      const from = this.element.querySelector('#date-from');
      const to = this.element.querySelector('#date-to');
      const ratio = Math.max(0, Math.min(1, (event.clientX - rangeTrack.getBoundingClientRect().left) / rangeTrack.clientWidth));
      const value = Math.round(Number(from.min) + ratio * (Number(from.max) - Number(from.min)));
      const target = Math.abs(value - Number(from.value)) <= Math.abs(value - Number(to.value)) ? from : to;
      target.value = value;
      target.dispatchEvent(new Event('change', { bubbles: true }));
    });
    this.element.querySelectorAll('[data-date-input]').forEach(input => input.onchange = () => {
      this.filterDateFrom = this.element.querySelector('[data-date-input="from"]').value;
      this.filterDateTo = this.element.querySelector('[data-date-input="to"]').value;
      this._saveFilterState();
      this.loadDashboard();
    });
    this.element.querySelectorAll('[data-category]').forEach(button => button.onclick = () => { this.filterCategory = [button.dataset.category]; this._saveFilterState(); this.loadDashboard(); });
    this.element.querySelectorAll('[data-user]').forEach(button => button.onclick = () => { this.filterUser = [button.dataset.user]; this._saveFilterState(); this.loadDashboard(); });
    this.element.querySelectorAll('[data-site]').forEach(button => button.onclick = () => { this.filterSite = [button.dataset.site]; this._saveFilterState(); this.loadDashboard(); });
    this.element.querySelector('[data-reset-filters]').onclick = () => { this.filterDateFrom = ''; this.filterDateTo = ''; this.filterUser = []; this.filterSite = []; this.filterCategory = []; localStorage.removeItem(this.filterStorageKey); this.loadDashboard(); };
    this._bindMultiFilters();
    this.element.querySelectorAll('[data-list-edit]').forEach(button => button.onclick = () => this.onEditExpense?.(this.expenses.find(item => item.id === Number(button.dataset.listEdit))));
    this.element.querySelectorAll('[data-list-delete]').forEach(button => button.onclick = () => this.onDeleteExpense?.(this.expenses.find(item => item.id === Number(button.dataset.listDelete))));
    this.element.querySelector('[data-expense-search]')?.addEventListener('change', event => { this.expenseSearch = event.target.value; this.expensePage = 1; this.loadDashboard(); });

  }

  _renderMultiFilter(key, label, options, selected) {
    const all = !selected.length;
    return `<div class="filter-group"><label class="filter-label">${label}</label><details class="dashboard-multi-filter" data-multi-filter="${key}"><summary data-filter-summary>${all ? 'Toutes' : `${selected.length} sélectionné(s)`}</summary><div class="dashboard-multi-filter-menu" data-filter-options><label><input type="checkbox" data-filter-all ${all ? 'checked' : ''}> Toutes</label>${options.map(option => `<label><input type="checkbox" data-filter-option value="${option}" ${selected.includes(option) ? 'checked' : ''}>${option}</label>`).join('')}</div></details></div>`;
  }

  _bindMultiFilters(keys = null) {
    this.element.querySelectorAll('[data-multi-filter]').forEach(container => {
      const key = container.dataset.multiFilter;
      if (keys && !keys.includes(key)) return;
      const allInput = container.querySelector('[data-filter-all]');
      const update = () => {
        const values = [...container.querySelectorAll('[data-filter-option]:checked')].map(input => input.value);
        if (key === 'category') this.filterCategory = values;
        if (key === 'user') this.filterUser = values;
        if (key === 'site') this.filterSite = values.map(Number);
        container.querySelector('[data-filter-summary]').textContent = values.length ? `${values.length} sélectionné(s)` : 'Toutes';
        this._saveFilterState();
        this.loadDashboard();
      };
      allInput?.addEventListener('change', () => {
        container.querySelectorAll('[data-filter-option]').forEach(input => { input.checked = false; });
        update();
      });
      container.querySelectorAll('[data-filter-option]').forEach(input => input.addEventListener('change', () => {
        if (input.checked && allInput) allInput.checked = false;
        update();
      }));
    });
  }

  _renderHistogram() {
    const canvas = this.element.querySelector('#monthly-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.clientWidth || 400;
    const height = 300;
    canvas.width = width;
    canvas.height = height;
    const padding = { top: 40, right: 40, bottom: 60, left: 60 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    ctx.clearRect(0, 0, width, height);
    const monthly = this.dashboard.monthly || [];
    if (!monthly.length) {
      ctx.fillStyle = '#6B7280';
      ctx.font = '14px system-ui';
      ctx.textAlign = 'center';
      ctx.fillText('Aucune dépense pour les filtres sélectionnés', width / 2, height / 2);
      return;
    }

    const max = Math.max(...monthly.map(item => item.amount), 1);
    const xScale = (i) => padding.left + (chartWidth / monthly.length) * (i + 0.5);

    // Axes
    ctx.strokeStyle = '#6B7280';
    ctx.lineWidth = 1;

    // Axis X
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top + chartHeight);
    ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight);
    ctx.stroke();

    // Axis Y
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top);
    ctx.lineTo(padding.left, padding.top + chartHeight);
    ctx.stroke();

    monthly.forEach((item, i) => {
      const cat = `${item.year}-${String(item.month).padStart(2, '0')}`;
      const x = xScale(i);
      const barWidth = Math.max(12, chartWidth / (monthly.length * 1.8));
      const barX = x - barWidth / 2;
      let currentY = padding.top + chartHeight;
      const categories = Object.entries(item.categories || {});
      categories.forEach(([category, amount], categoryIndex) => {
        const segmentHeight = (amount / max) * chartHeight;
        ctx.fillStyle = this._chartColor(this._monthlyCategoryIndex(category));
        currentY -= segmentHeight;
        ctx.fillRect(barX, currentY, barWidth, segmentHeight);
      });
      
      // Label catégorie
      ctx.fillStyle = '#374151';
      ctx.font = '11px system-ui';
      ctx.textAlign = 'center';
      ctx.fillText(cat, barX + barWidth / 2, padding.top + chartHeight + 18);
      
      // Valeur
      ctx.fillStyle = '#1F2937';
      ctx.font = '11px system-ui';
      ctx.textAlign = 'center';
      ctx.fillText(
        Math.round(item.amount),
        barX + barWidth / 2,
        padding.top - 5
      );
    });

  }

  _monthlyCategoryIndex(category) {
    const categories = [...new Set((this.dashboard.monthly || []).flatMap(item => Object.keys(item.categories || {})))];
    return categories.indexOf(category);
  }

  _renderMonthlyLegend() {
    const categories = [...new Set((this.dashboard.monthly || []).flatMap(item => Object.keys(item.categories || {})))];
    return categories.map(category => `<span class="chart-legend-item"><i class="chart-swatch" style="background:${this._chartColor(this._monthlyCategoryIndex(category))}"></i>${category}</span>`).join('') || '<span class="chart-legend-item">Aucune donnée</span>';
  }

  _money(value) { return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(Number(value) || 0); }
  _renderKpis() {
    const k = this.dashboard.kpis || {}; const top = (this.dashboard.categories || [])[0];
    const from = this.filterDateFrom ? new Date(`${this.filterDateFrom}T00:00:00`) : null;
    const to = this.filterDateTo ? new Date(`${this.filterDateTo}T00:00:00`) : null;
    const dailyMode = from && to && Math.round((to - from) / 86400000) < 31;
    const periods = dailyMode ? (this.dashboard.daily || []) : (this.dashboard.monthly || []);
    const periodCount = periods.length ? periods.reduce((sum, item) => sum + Number(item.count || 0), 0) : Number(k.count || 0);
    const periodAverage = periods.length ? periods.reduce((sum, item) => sum + Number(item.amount || 0), 0) / periods.length : Number(k.average_amount || 0);
    const periodLabel = dailyMode ? 'jour' : 'mois';
    const share = k.total_amount && top ? `${(top.amount / k.total_amount * 100).toFixed(1)} % du total` : '—';
    const previous = k.previous_amount == null ? 'Comparaison indisponible' : `Période précédente : ${this._money(k.previous_amount)}`;
    return `<article class="intendance-kpi-card"><span>Total</span><strong>${this._money(k.total_amount)}</strong></article><article class="intendance-kpi-card"><span>Nb d'opérations par ${periodLabel}</span><strong>${periodCount}</strong></article><article class="intendance-kpi-card"><span>Moyenne des dépenses par ${periodLabel}</span><strong>${this._money(periodAverage)}</strong></article><article class="intendance-kpi-card"><span>Catégorie principale</span><strong>${top ? top.name : '—'}</strong><small>${top ? `${this._money(top.amount)} · ${share}` : 'Aucune donnée'}</small></article><article class="intendance-kpi-card"><span>Comparaison</span><strong>${previous}</strong></article>`;
  }
  _renderCategoryBars() {
    const total = this.dashboard.kpis?.total_amount || 0;
    return (this.dashboard.categories || []).map((item, index) => `<button type="button" class="intendance-bar-row" data-category="${item.name}"><span class="intendance-bar-label"><i class="chart-swatch" style="background:${this._chartColor(index)}"></i>${item.name}</span><i class="intendance-bar-track"><b style="width:${total ? item.amount / total * 100 : 0}%;background:${this._chartColor(index)}"></b></i><strong>${this._money(item.amount)}</strong><small>${total ? (item.amount / total * 100).toFixed(1) : 0}%</small></button>`).join('') || '<p class="text-muted">Aucune dépense.</p>';
  }
  _renderUserBars() { return (this.dashboard.users || []).map((item, index) => `<button type="button" class="intendance-bar-row" data-user="${item.name}"><span class="intendance-bar-label"><i class="chart-swatch" style="background:${this._chartColor(index + 2)}"></i>${item.name}</span><i class="intendance-bar-track"><b style="width:${this.dashboard.users[0]?.amount ? item.amount / this.dashboard.users[0].amount * 100 : 0}%;background:${this._chartColor(index + 2)}"></b></i><strong>${this._money(item.amount)}</strong><small>${item.count} dép.</small></button>`).join('') || '<p class="text-muted">Aucune attribution utilisateur.</p>'; }
  _renderSiteBars() { const sites = this.dashboard.sites || []; const max = Math.max(...sites.map(item => Number(item.amount) || 0), 1); return sites.map((item, index) => `<button type="button" class="intendance-bar-row" data-site="${item.name}"><span class="intendance-bar-label"><i class="chart-swatch" style="background:${this._chartColor(index)}"></i>${item.name}</span><i class="intendance-bar-track"><b style="width:${(Number(item.amount) || 0) / max * 100}%;background:${this._chartColor(index)}"></b></i><strong>${this._money(item.amount)}</strong><small>${item.count} op.</small></button>`).join('') || '<p class="text-muted">Aucune dépense d’énergie affectée à un site.</p>'; }
  _renderMealCostBySite() {
    if (this.mealSiteCostsUnavailable) return '<p class="text-muted">Votre compte doit avoir accès aux modules Agenda et Bâtiments pour consulter ce calcul.</p>';
    const rows = this.mealSiteCosts || [];
    const max = Math.max(...rows.map(item => Number(item.cost_per_person) || 0), 1);
    return rows.map((item, index) => `<div class="intendance-bar-row" title="${this._money(item.amount)} de nourriture · ${item.meal_count} repas déclarés"><span class="intendance-bar-label"><i class="chart-swatch" style="background:${this._chartColor(index + 1)}"></i>${item.name}</span><i class="intendance-bar-track"><b style="width:${item.cost_per_person == null ? 0 : Number(item.cost_per_person) / max * 100}%;background:${this._chartColor(index + 1)}"></b></i><strong>${item.cost_per_person == null ? '—' : this._money(item.cost_per_person)}</strong><small>${item.meal_count} pers.</small></div>`).join('') || '<p class="text-muted">Aucun site mappé à un local Bureau/Logement ou aucune donnée pour cette période.</p>';
  }
  _chartColor(index) { return ['#2563eb', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2', '#db2777', '#65a30d'][index % 8]; }
  _renderTopExpenses() { return `<div class="table-container"><table class="users-table"><thead><tr><th>Date</th><th>Libellé</th><th>Catégorie</th><th>Utilisateur</th><th>Montant</th></tr></thead><tbody>${(this.dashboard.top_expenses || []).map(item => `<tr><td>${item.date}</td><td>${item.description || ''}</td><td>${item.category}</td><td>${item.user_name || '—'}</td><td>${this._money(item.amount)}</td></tr>`).join('') || '<tr><td colspan="5">Aucune dépense.</td></tr>'}</tbody></table></div>`; }
  _renderSummary() { const total = this.dashboard.kpis?.total_amount || 0; return `<div class="table-container"><table class="users-table"><thead><tr><th>Catégorie</th><th>Nombre</th><th>Total</th><th>Part</th><th>Moyenne</th></tr></thead><tbody>${(this.dashboard.categories || []).map(item => `<tr><td>${item.name}</td><td>${item.count}</td><td>${this._money(item.amount)}</td><td>${total ? (item.amount / total * 100).toFixed(1) : 0}%</td><td>${this._money(item.average)}</td></tr>`).join('')}</tbody></table></div>`; }
  _renderExpenseList() { return `<div class="page-filters"><input class="form-input" type="search" data-expense-search placeholder="Rechercher une dépense…" value="${this.expenseSearch}"></div><div data-expense-table></div>`; }

  _loadUsersSites() {
    Promise.all([listAliases(), listSites()]).then(([aliases, sites]) => {
      const users = [...new Set((aliases.items || []).map(item => item.user_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'));
      const userOptions = this.element.querySelector('[data-multi-filter="user"] [data-filter-options]');
      const siteOptions = this.element.querySelector('[data-multi-filter="site"] [data-filter-options]');
      const visibleUsers = [...new Set((aliases.items || []).filter(item => item.dashboard_visible !== false).map(item => item.user_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'));
      if (userOptions) userOptions.innerHTML = `<label><input type="checkbox" data-filter-all ${this.filterUser.length ? '' : 'checked'}> Toutes</label>${visibleUsers.map(user => `<label><input type="checkbox" data-filter-option value="${user}" ${this.filterUser.includes(user) ? 'checked' : ''}>${user}</label>`).join('')}`;
      if (siteOptions) siteOptions.innerHTML = `<label><input type="checkbox" data-filter-all ${this.filterSite.length ? '' : 'checked'}> Toutes</label>${(sites.items || []).filter(site => site.dashboard_visible !== false).map(site => `<label><input type="checkbox" data-filter-option value="${site.id}" ${this.filterSite.includes(Number(site.id)) ? 'checked' : ''}>${site.name}</label>`).join('')}`;
      this._bindMultiFilters(['user', 'site']);
    });
    this._updateDateRangeTrack();
  }

  _updateDateRangeTrack() {
    const from = this.element.querySelector('#date-from'); const to = this.element.querySelector('#date-to'); const track = this.element.querySelector('.date-range-sliders');
    if (!from || !to || !track) return;
    const min = Number(from.min); const max = Number(from.max); const start = ((Math.min(Number(from.value), Number(to.value)) - min) / (max - min)) * 100; const end = ((Math.max(Number(from.value), Number(to.value)) - min) / (max - min)) * 100;
    track.style.setProperty('--range-start', `${start}%`); track.style.setProperty('--range-end', `${end}%`);
  }
}

export const createIntendanceDashboardPage = options => new IntendanceDashboardPage(options);
