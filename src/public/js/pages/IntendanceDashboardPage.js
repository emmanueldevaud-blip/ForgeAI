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
    this.filterDateFrom = '';
    this.filterDateTo = '';
    this.filterUser = '';
    this.filterSite = '';
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
    if (this.filterUser) params.append('user_name', this.filterUser);
    if (this.filterSite) params.append('site_id', this.filterSite);

    const categories = (await getExpenseDashboard(Object.fromEntries(params))) || {};

    this.categories = Object.keys(categories).filter(category => category && category !== 'undefined');
    this.categories.sort((a, b) => Number(categories[b] || 0) - Number(categories[a] || 0));
    this.amounts = this.categories.map(cat => Number(categories[cat]) || 0);
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
          <div class="filter-group">
            <label class="filter-label">Période</label>
            <div class="slider-wrapper">
              <div class="date-range-values"><input type="date" class="date-range-calendar" data-date-input="from" value="${dateFromStr}" aria-label="Date de début"><span>–</span><input type="date" class="date-range-calendar" data-date-input="to" value="${dateToStr}" aria-label="Date de fin"></div>
              <div class="date-range-sliders"><input type="range" id="date-from" min="0" max="${rangeMax}" value="${dateFromValue}" aria-label="Date de début"><input type="range" id="date-to" min="0" max="${rangeMax}" value="${dateToValue}" aria-label="Date de fin"></div>
            </div>
          </div>
          <div class="filter-group">
            <label class="filter-label">Utilisateur</label>
            <select class="form-select" id="user-filter">
              <option value="">Tous</option>
            </select>
          </div>
          <div class="filter-group">
            <label class="filter-label">Site</label>
            <select class="form-select" id="site-filter">
              <option value="">Tous</option>
            </select>
          </div>
        </div>

        <!-- Histogramme -->
        <div class="histogram-container">
          <canvas id="category-histogram" style="display:block;width:100%;height:300px"></canvas>
          <div class="histogram-legend"></div>
        </div>
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
      input.onchange = () => {
        const start = new Date('2020-01-01');
        const toDate = value => new Date(start.getTime() + Number(value) * 86400000).toISOString().split('T')[0];
        const fromValue = Number(document.getElementById('date-from').value);
        const toValue = Number(document.getElementById('date-to').value);
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

    // User filter
    this.element.querySelector('#user-filter').onchange = (e) => {
      this.filterUser = e.target.value;
      this.loadDashboard();
    };

    // Site filter
    this.element.querySelector('#site-filter').onchange = (e) => {
      this.filterSite = e.target.value;
      this.loadDashboard();
    };

    // Close button
    this.element.querySelector('[data-close-dashboard]').onclick = () => {
      clearInterval(this.refreshTimer);
      this.element.remove();
    };
  }

  _renderHistogram() {
    const canvas = this.element.querySelector('#category-histogram');
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
    if (!this.categories.length) {
      ctx.fillStyle = '#6B7280';
      ctx.font = '14px system-ui';
      ctx.textAlign = 'center';
      ctx.fillText('Aucune dépense pour les filtres sélectionnés', width / 2, height / 2);
      return;
    }

    // Échelles
    const xScale = (i) => padding.left + (chartWidth / (this.categories.length - 1)) * i;
    const yScale = (amount) => padding.top + chartHeight - (amount / this.maxAmount) * chartHeight;

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

    // Barres
    this.categories.forEach((cat, i) => {
      const x = xScale(i);
      const barWidth = chartWidth / (this.categories.length + 1);
      const barX = x - barWidth / 2;
      const barHeight = (this.amounts[i] / this.maxAmount) * chartHeight;
      
      ctx.fillStyle = getCategoryColor(cat);
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
        Math.round(this.amounts[i]),
        barX + barWidth / 2,
        padding.top - 5
      );
    });

  }

  _loadUsersSites() {
    Promise.all([listAliases(), listSites()]).then(([aliases, sites]) => {
      const users = [...new Set((aliases.items || []).map(item => item.user_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'));
      const userSelect = this.element.querySelector('#user-filter');
      const siteSelect = this.element.querySelector('#site-filter');
      if (userSelect) userSelect.innerHTML = '<option value="">Tous</option>' + users.map(user => `<option value="${user}">${user}</option>`).join('');
      if (siteSelect) siteSelect.innerHTML = '<option value="">Tous</option>' + (sites.items || []).map(site => `<option value="${site.id}">${site.name}</option>`).join('');
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
