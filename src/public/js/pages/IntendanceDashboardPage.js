import { authStore } from '../stores/auth.js';
import { getExpenseDashboard, listAliases, listSites } from '../services/intendanceApi.js';

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
  constructor() {
    this.element = null;
    this.categories = [];
    this.amounts = [];
    this.maxAmount = 0;
    this.dashboard = { kpis: {}, categories: [], monthly: [], users: [], top_expenses: [] };
    this.filterDateFrom = '';
    this.filterDateTo = '';
    this.filterUser = [];
    this.filterSite = [];
    this.filterCategory = [];
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
    if (this.filterDateFrom) params.append('expense_date_from', this.filterDateFrom);
    if (this.filterDateTo) params.append('expense_date_to', this.filterDateTo);
    this.filterUser.forEach(user => params.append('user_name', user));
    this.filterSite.forEach(site => params.append('site_id', site));
    this.filterCategory.forEach(category => params.append('category', category));

    this.dashboard = (await getExpenseDashboard(params)) || this.dashboard;
    const categories = this.dashboard.categories || [];
    this.categories = categories.map(item => item.name);
    this.amounts = categories.map(item => Number(item.amount) || 0);
    this.maxAmount = Math.max(...this.amounts, 1);

    this.render();
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

    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Tableau de bord des dépenses</h1>
          <p class="page-subtitle">Suivi des catégories de dépenses</p>
        </div>
        <div class="page-header-right">
          <button class="btn btn-secondary" data-close-dashboard>← Retour</button>
        </div>
      </div>

      <div class="dashboard-container">
        <!-- Filtres -->
        <div class="dashboard-filters">
          <div class="dashboard-filters-row dashboard-filters-row--top">
          <div class="filter-group">
            <label class="filter-label">Catégorie</label>
            <select class="form-select" id="category-filter">
              <option value="">Toutes</option>
              ${(this.dashboard.categories || []).map(item => `<option value="${item.name}" ${this.filterCategory.includes(item.name) ? 'selected' : ''}>${item.name}</option>`).join('')}
            </select>
          </div>
          <div class="filter-group">
            <label class="filter-label">Période</label>
            <div class="slider-wrapper">
              <div class="date-range-values"><input type="date" class="date-range-calendar" data-date-input="from" value="${dateFromStr}" aria-label="Date de début"><span>–</span><input type="date" class="date-range-calendar" data-date-input="to" value="${dateToStr}" aria-label="Date de fin"></div>
              <div class="date-range-sliders"><input type="range" id="date-from" min="0" max="${rangeMax}" value="${dateFromValue}" aria-label="Date de début"><input type="range" id="date-to" min="0" max="${rangeMax}" value="${dateToValue}" aria-label="Date de fin"></div>
            </div>
          </div>
          </div>
          <div class="dashboard-filters-row dashboard-filters-row--bottom">
          <div class="filter-group">
            <label class="filter-label">Utilisateur</label>
            <select class="form-select" id="user-filter" multiple size="4" aria-label="Utilisateurs">
              <option value="">Tous</option>
            </select>
          </div>
          <div class="filter-group">
            <label class="filter-label">Site</label>
            <select class="form-select" id="site-filter" multiple size="4" aria-label="Sites">
              <option value="">Tous</option>
            </select>
          </div>
          <button type="button" class="btn btn-secondary" data-reset-filters>Réinitialiser</button>
          </div>
        </div>

        <div class="intendance-kpi-grid">${this._renderKpis()}</div>
        <div class="intendance-dashboard-grid">
          <section class="histogram-container chart-card"><div class="chart-heading"><div><h2>Évolution mensuelle</h2><p>Montant total dépensé par mois</p></div><div class="chart-legend"><span class="chart-legend-item"><i class="chart-swatch chart-swatch--primary"></i>Montant (€)</span></div></div><canvas id="monthly-chart" aria-label="Évolution mensuelle des dépenses"></canvas></section>
          <section class="histogram-container chart-card"><div class="chart-heading"><div><h2>Répartition par catégorie</h2><p>Cliquer sur une catégorie pour filtrer</p></div><div class="chart-legend"><span class="chart-legend-item"><i class="chart-swatch chart-swatch--category"></i>Part du total</span></div></div>${this._renderCategoryBars()}</section>
          <section class="histogram-container chart-card"><div class="chart-heading"><div><h2>Répartition par utilisateur</h2><p>Montant attribué et nombre de dépenses</p></div><div class="chart-legend"><span class="chart-legend-item"><i class="chart-swatch chart-swatch--user"></i>Montant (€)</span></div></div>${this._renderUserBars()}</section>
        </div>
        <section class="histogram-container intendance-summary"><h2>Synthèse par catégorie</h2>${this._renderSummary()}</section>
      </div>
    `;

    this._bind();
    this._renderHistogram();
    this._loadUsersSites();
    return this.element;
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
        this._updateDateRangeTrack();
        this.element.querySelector('[data-date-input="from"]').value = this.filterDateFrom;
        this.element.querySelector('[data-date-input="to"]').value = this.filterDateTo;
        this.loadDashboard();
      };
    });
    this.element.querySelectorAll('[data-date-input]').forEach(input => input.onchange = () => {
      this.filterDateFrom = this.element.querySelector('[data-date-input="from"]').value;
      this.filterDateTo = this.element.querySelector('[data-date-input="to"]').value;
      this.loadDashboard();
    });
    this.element.querySelector('#category-filter').onchange = event => { this.filterCategory = event.target.value ? [event.target.value] : []; this.loadDashboard(); };
    this.element.querySelectorAll('[data-category]').forEach(button => button.onclick = () => { this.filterCategory = [button.dataset.category]; this.loadDashboard(); });
    this.element.querySelector('[data-reset-filters]').onclick = () => { this.filterDateFrom = ''; this.filterDateTo = ''; this.filterUser = []; this.filterSite = []; this.filterCategory = []; this.loadDashboard(); };

    // User filter
    this.element.querySelector('#user-filter').onchange = (e) => {
      this.filterUser = Array.from(e.target.selectedOptions, option => option.value);
      this.loadDashboard();
    };

    // Site filter
    this.element.querySelector('#site-filter').onchange = (e) => {
      this.filterSite = Array.from(e.target.selectedOptions, option => Number(option.value));
      this.loadDashboard();
    };

    // Close button
    this.element.querySelector('[data-close-dashboard]').onclick = () => {
      clearInterval(this.refreshTimer);
      this.element.remove();
    };
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
    const xScale = (i) => padding.left + (chartWidth / Math.max(monthly.length - 1, 1)) * i;

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
      const barHeight = (item.amount / max) * chartHeight;
      
      ctx.fillStyle = 'var(--color-primary)';
      ctx.fillStyle = '#4F46E5';
      ctx.fillRect(barX, padding.top + chartHeight - barHeight, barWidth, barHeight);
      
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

  _money(value) { return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(Number(value) || 0); }
  _renderKpis() {
    const k = this.dashboard.kpis || {}; const top = (this.dashboard.categories || [])[0];
    const share = k.total_amount && top ? `${(top.amount / k.total_amount * 100).toFixed(1)} % du total` : '—';
    const previous = k.previous_amount == null ? 'Comparaison indisponible' : `Période précédente : ${this._money(k.previous_amount)}`;
    return `<article class="intendance-kpi-card"><span>Total</span><strong>${this._money(k.total_amount)}</strong></article><article class="intendance-kpi-card"><span>Dépenses</span><strong>${k.count || 0}</strong></article><article class="intendance-kpi-card"><span>Moyenne</span><strong>${this._money(k.average_amount)}</strong></article><article class="intendance-kpi-card"><span>Catégorie principale</span><strong>${top ? top.name : '—'}</strong><small>${top ? `${this._money(top.amount)} · ${share}` : 'Aucune donnée'}</small></article><article class="intendance-kpi-card"><span>Comparaison</span><strong>${previous}</strong></article>`;
  }
  _renderCategoryBars() {
    const total = this.dashboard.kpis?.total_amount || 0;
    return (this.dashboard.categories || []).map((item, index) => `<button type="button" class="intendance-bar-row" data-category="${item.name}"><span class="intendance-bar-label"><i class="chart-swatch" style="background:${this._chartColor(index)}"></i>${item.name}</span><i class="intendance-bar-track"><b style="width:${total ? item.amount / total * 100 : 0}%;background:${this._chartColor(index)}"></b></i><strong>${this._money(item.amount)}</strong><small>${total ? (item.amount / total * 100).toFixed(1) : 0}%</small></button>`).join('') || '<p class="text-muted">Aucune dépense.</p>';
  }
  _renderUserBars() { return (this.dashboard.users || []).map((item, index) => `<div class="intendance-bar-row"><span class="intendance-bar-label"><i class="chart-swatch" style="background:${this._chartColor(index + 2)}"></i>${item.name}</span><i class="intendance-bar-track"><b style="width:${this.dashboard.users[0]?.amount ? item.amount / this.dashboard.users[0].amount * 100 : 0}%;background:${this._chartColor(index + 2)}"></b></i><strong>${this._money(item.amount)}</strong><small>${item.count} dép.</small></div>`).join('') || '<p class="text-muted">Aucune attribution utilisateur.</p>'; }
  _chartColor(index) { return ['#2563eb', '#7c3aed', '#059669', '#d97706', '#dc2626', '#0891b2', '#db2777', '#65a30d'][index % 8]; }
  _renderTopExpenses() { return `<div class="table-container"><table class="users-table"><thead><tr><th>Date</th><th>Libellé</th><th>Catégorie</th><th>Utilisateur</th><th>Montant</th></tr></thead><tbody>${(this.dashboard.top_expenses || []).map(item => `<tr><td>${item.date}</td><td>${item.description || ''}</td><td>${item.category}</td><td>${item.user_name || '—'}</td><td>${this._money(item.amount)}</td></tr>`).join('') || '<tr><td colspan="5">Aucune dépense.</td></tr>'}</tbody></table></div>`; }
  _renderSummary() { const total = this.dashboard.kpis?.total_amount || 0; return `<div class="table-container"><table class="users-table"><thead><tr><th>Catégorie</th><th>Nombre</th><th>Total</th><th>Part</th><th>Moyenne</th></tr></thead><tbody>${(this.dashboard.categories || []).map(item => `<tr><td>${item.name}</td><td>${item.count}</td><td>${this._money(item.amount)}</td><td>${total ? (item.amount / total * 100).toFixed(1) : 0}%</td><td>${this._money(item.average)}</td></tr>`).join('')}</tbody></table></div>`; }

  _loadUsersSites() {
    Promise.all([listAliases(), listSites()]).then(([aliases, sites]) => {
      const users = [...new Set((aliases.items || []).map(item => item.user_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'));
      const userSelect = this.element.querySelector('#user-filter');
      const siteSelect = this.element.querySelector('#site-filter');
      if (userSelect) {
        userSelect.innerHTML = users.map(user => `<option value="${user}">${user}</option>`).join('');
        Array.from(userSelect.options).forEach(option => { option.selected = this.filterUser.includes(option.value); });
      }
      if (siteSelect) {
        siteSelect.innerHTML = (sites.items || []).map(site => `<option value="${site.id}">${site.name}</option>`).join('');
        Array.from(siteSelect.options).forEach(option => { option.selected = this.filterSite.includes(Number(option.value)); });
      }
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

export const createIntendanceDashboardPage = () => new IntendanceDashboardPage();
