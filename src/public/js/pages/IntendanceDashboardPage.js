import { authStore } from '../stores/auth.js';
import { listExpenses } from '../services/intendanceApi.js';

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
  }

  async init() {
    await this.loadDashboard();
  }

  async loadDashboard() {
    const params = new URLSearchParams();
    if (this.filterDateFrom) params.append('expense_date_from', this.filterDateFrom);
    if (this.filterDateTo) params.append('expense_date_to', this.filterDateTo);
    if (this.filterUser) params.append('user_name', this.filterUser);
    if (this.filterSite) params.append('site_id', this.filterSite);

    const data = await listExpenses(params);
    const categories = {};
    
    for (const expense of data.items || []) {
      const cat = expense.category || 'Non classé';
      categories[cat] = (categories[cat] || 0) + expense.amount;
    }

    this.categories = Object.keys(categories).sort((a, b) => categories[b] - categories[a]);
    this.amounts = this.categories.map(cat => categories[cat] || 0);
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
              <input type="date" id="date-from" class="form-input" value="${dateFromStr}" />
              <span class="slider-separator">–</span>
              <input type="date" id="date-to" class="form-input" value="${dateToStr}" />
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
          <canvas id="category-histogram"></canvas>
          <div class="histogram-legend"></div>
        </div>
      </div>
    `;

    this._bind();
    this._renderHistogram();
    this._loadUsersSites();
  }

  _bind() {
    const dashboard = this;
    
    // Date filter
    this.element.querySelectorAll('#date-from, #date-to').forEach(input => {
      input.onchange = () => {
        this.filterDateFrom = document.getElementById('date-from').value;
        this.filterDateTo = document.getElementById('date-to').value;
        this.loadDashboard();
      };
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
    const padding = { top: 40, right: 40, bottom: 60, left: 60 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    ctx.clearRect(0, 0, width, height);

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

    // Légende
    const legendCtx = this.element.querySelector('.histogram-legend')?.getContext('2d') || {};
    // On peut ajouter une légende SVG si nécessaire
  }

  _loadUsersSites() {
    // Charger les utilisateurs et sites uniques depuis les dépenses
    // Cela se fait via l'API au chargement
  }
}

export const createIntendanceDashboardPage = () => new IntendanceDashboardPage();
