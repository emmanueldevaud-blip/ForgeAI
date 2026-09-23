import { authStore } from '../stores/auth.js';
import { getDashboardWidgets, getWidgetData } from '../services/dashboardApi.js';

const MODULE_LABELS = {
  buildings: 'Bâtiments',
  equipment: 'Équipements',
  housing: 'Hébergements',
  maintenance: 'Maintenance',
};

const MODULE_ORDER = ['buildings', 'equipment', 'housing', 'maintenance'];

function formatValue(value, widgetType) {
  if (value === null || value === undefined) return '-';
  if (widgetType === 'occupancy_rate' || String(value).includes('%')) return `${value}%`;
  if (typeof value === 'number' && value >= 1000) {
    return value.toLocaleString('fr-FR');
  }
  return value;
}

export class DashboardPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.widgets = [];
    this.widgetData = {};
    this._authUnsubscribe = null;
    this._loading = false;
  }

  async initialize() {
    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element && !this._loading) {
        this.loadData();
      }
    });
  }

  async loadData() {
    if (this._loading) return;
    this._loading = true;

    try {
      this.widgets = await getDashboardWidgets();
      this.widgetData = {};

      const fetches = this.widgets.map(async (w) => {
        try {
          const result = await getWidgetData(w.id);
          this.widgetData[w.id] = result.data;
        } catch (e) {
          console.error(`Erreur chargement widget ${w.id}:`, e);
          this.widgetData[w.id] = null;
        }
      });

      await Promise.all(fetches);
      this._renderWidgets();
    } catch (error) {
      console.error('Erreur chargement tableau de bord:', error);
    } finally {
      this._loading = false;
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Tableau de bord</h1>
          <p class="page-subtitle">Vue d'ensemble de ForgeAI</p>
        </div>
      </div>
      <div class="dashboard-loading" data-loading>
        <div class="spinner" aria-hidden="true"></div>
        <p>Préparation de votre tableau de bord...</p>
      </div>
      <div class="dashboard-modules" data-modules style="display:none"></div>
    `;
    return this.element;
  }

  _renderWidgets() {
    if (!this.element) return;

    const loadingEl = this.element.querySelector('[data-loading]');
    const modulesEl = this.element.querySelector('[data-modules]');
    if (!loadingEl || !modulesEl) return;

    loadingEl.style.display = 'none';
    modulesEl.style.display = '';

    if (this.widgets.length === 0) {
      modulesEl.innerHTML = `
        <div class="dashboard-empty">
          <div class="dashboard-empty-icon" aria-hidden="true">▦</div>
          <h2>Votre tableau de bord est prêt à être personnalisé</h2>
          <p>Les indicateurs disponibles apparaîtront ici selon vos accès.</p>
        </div>
      `;
      return;
    }

    const grouped = {};
    for (const w of this.widgets) {
      if (!grouped[w.module]) grouped[w.module] = [];
      grouped[w.module].push(w);
    }

    const sortedModules = MODULE_ORDER.filter((m) => grouped[m]);

    modulesEl.innerHTML = sortedModules.map((moduleCode) => {
      const widgets = grouped[moduleCode];
      const label = MODULE_LABELS[moduleCode] || moduleCode;
      return `
        <div class="dashboard-module-section">
          <h2 class="dashboard-module-title">${label}</h2>
          <div class="dashboard-widget-grid">
            ${widgets.map((w) => this._renderWidget(w)).join('')}
          </div>
        </div>
      `;
    }).join('');
  }

  _renderWidget(widget) {
    const data = this.widgetData[widget.id];
    const value = data ? this._extractValue(widget, data) : null;
    const displayValue = formatValue(value, widget.id);

    const isAlert = widget.widget_type === 'alert';
    const alertClass = isAlert && value && value > 0 ? 'widget--alert-active' : '';

    return `
      <div class="widget widget--${widget.widget_type} widget--${widget.width} ${alertClass}"
           data-widget-id="${widget.id}" role="article"
           ${widget.link ? `data-link="${widget.link}"` : ''}>
        <div class="widget-header">
          <span class="widget-icon">${this._getIcon(widget.icon)}</span>
          <span class="widget-title">${widget.title}</span>
        </div>
        <div class="widget-body">
          <div class="widget-value">${displayValue}</div>
          <div class="widget-description">${widget.description}</div>
        </div>
        ${widget.link ? `<a class="widget-link" href="${widget.link}" data-navigate>Voir</a>` : ''}
      </div>
    `;
  }

  _extractValue(widget, data) {
    const keyMap = {
      'building.total': 'total_buildings',
      'building.rooms': 'total_rooms',
      'equipment.total': 'total',
      'equipment.breakdown': 'breakdown',
      'equipment.inactive': 'inactive',
      'housing.occupied': 'occupied',
      'housing.free': 'free',
      'housing.arrivals': 'arrivals',
      'housing.departures': 'departures',
      'housing.to_clean': 'to_clean',
      'housing.occupancy_rate': 'occupancy_rate',
      'maintenance.open_requests': 'open_requests',
      'maintenance.open_work_orders': 'open_work_orders',
      'maintenance.overdue': 'overdue',
      'maintenance.preventive_due': 'preventive_due',
    };
    const key = keyMap[widget.id];
    return key ? data[key] : null;
  }

  _getIcon(iconName) {
    const icons = {
      dashboard: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect></svg>',
      building: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect><path d="M9 22v-4h6v4"></path><path d="M8 6h.01"></path><path d="M16 6h.01"></path><path d="M12 6h.01"></path><path d="M12 10h.01"></path><path d="M12 14h.01"></path><path d="M16 10h.01"></path><path d="M16 14h.01"></path><path d="M8 10h.01"></path><path d="M8 14h.01"></path></svg>',
      home: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
      wrench: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
      tool: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
      sparkles: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3z"></path></svg>',
    };
    return icons[iconName] || icons.dashboard;
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
    this.widgets = [];
    this.widgetData = {};
  }
}

export function createDashboardPage(router) {
  return new DashboardPage(router);
}
