import { authStore } from '../stores/auth.js';
import { getDashboardWidgets, getWidgetData } from '../services/dashboardApi.js';

const MODULE_META = {
  housing: { label: 'Hébergements', icon: 'home', color: 'success', route: '/housing' },
  maintenance: { label: 'Maintenance', icon: 'wrench', color: 'warning', route: '/maintenance' },
  agenda: { label: 'Agenda', icon: 'calendar-days', color: 'info', route: '/agenda' },
  equipment: { label: 'Équipements', icon: 'tool', color: 'danger', route: '/equipment' },
  buildings: { label: 'Bâtiments', icon: 'building', color: 'primary', route: '/buildings' },
  sport: { label: 'Sport', icon: 'run', color: 'danger', route: '/sport' },
  volunteers: { label: 'Volontaires', icon: 'users', color: 'success', route: '/volunteers' },
  administratif: { label: 'Administratif', icon: 'clipboard', color: 'primary', route: '/administratif' },
};

const MODULE_ORDER = ['housing', 'maintenance', 'agenda', 'equipment', 'buildings', 'sport', 'volunteers', 'administratif'];

const SECTION_EXCLUDED = {
  housing: ['housing.free'],
};

const HERO_PRIORITY = [
  'housing.occupancy_rate',
  'housing.occupied',
  'maintenance.open_requests',
  'equipment.breakdown',
  'agenda.today',
];

const VALUE_KEYS = {
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
  'agenda.today': 'today_count',
  'agenda.meals': 'meals_today',
  'volunteers.active': 'active',
  'sport.week': 'week_activities',
  'administrative.sessions': 'month_sessions',
};

const ALERT_RULES = [
  { id: 'maintenance.overdue', severity: 'danger', text: (v) => `${v} ordre${v > 1 ? 's' : ''} de travail en retard`, link: '/maintenance/work-orders' },
  { id: 'equipment.breakdown', severity: 'danger', text: (v) => `${v} équipement${v > 1 ? 's' : ''} en panne`, link: '/equipment' },
  { id: 'equipment.inactive', severity: 'warning', text: (v) => `${v} équipement${v > 1 ? 's' : ''} hors service`, link: '/equipment' },
  { id: 'housing.to_clean', severity: 'warning', text: (v) => `${v} ménage${v > 1 ? 's' : ''} à planifier`, link: '/housing/cleaning' },
  { id: 'maintenance.preventive_due', severity: 'info', text: (v) => `${v} entretien${v > 1 ? 's' : ''} préventif${v > 1 ? 's' : ''} à prévoir`, link: '/maintenance/preventive' },
  { id: 'agenda.meals', severity: 'info', text: (v) => `${v} repas${v > 1 ? 's' : ''} à prévoir aujourd’hui`, link: '/agenda' },
];

function formatValue(value, widgetId) {
  if (value === null || value === undefined) return '-';
  if (widgetId === 'housing.occupancy_rate') return `${value} %`;
  if (typeof value === 'number' && value >= 1000) return value.toLocaleString('fr-FR');
  return value;
}

function todayLabel() {
  return new Intl.DateTimeFormat('fr-FR', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  }).format(new Date());
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
    this.element.className = 'page-content dashboard-page';
    this.element.innerHTML = `
      <div class="page-header dash-header">
        <div class="page-header-left">
          <h1>Tableau de bord</h1>
          <p class="page-subtitle">Vue d’ensemble de ForgeAI — ${todayLabel()}</p>
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

  _widgetValue(widget) {
    const data = this.widgetData[widget.id];
    if (!data) return null;
    const key = VALUE_KEYS[widget.id];
    return key ? data[key] : null;
  }

  _widgetData(widgetId) {
    return this.widgetData[widgetId] || null;
  }

  _collectAlerts() {
    const alerts = [];
    for (const rule of ALERT_RULES) {
      const widget = this.widgets.find((w) => w.id === rule.id);
      if (!widget) continue;
      const value = this._widgetValue(widget);
      if (typeof value === 'number' && value > 0) {
        alerts.push({ severity: rule.severity, text: rule.text(value), link: rule.link });
      }
    }
    return alerts;
  }

  _heroCards() {
    const cards = [];
    const pick = (id) => this.widgets.find((w) => w.id === id);

    const rate = pick('housing.occupancy_rate');
    if (rate) {
      const value = this._widgetValue(rate);
      cards.push({
        id: rate.id,
        label: 'Taux d’occupation',
        value: formatValue(value, rate.id),
        link: rate.link,
        color: 'success',
        progress: typeof value === 'number' ? value : null,
        icon: 'home',
      });
    }

    const occupied = pick('housing.occupied');
    if (occupied) {
      const data = this._widgetData('housing.occupied') || {};
      const ratio = data.total ? Math.round(((data.occupied || 0) / data.total) * 100) : null;
      cards.push({
        id: occupied.id,
        label: 'Logements occupés',
        value: `${this._widgetValue(occupied) ?? '-'} / ${data.total ?? '-'}`,
        sub: 'hébergements actifs',
        link: occupied.link,
        color: 'success',
        progress: ratio,
        icon: 'home',
      });
    }

    const requests = pick('maintenance.open_requests');
    if (requests) {
      const value = this._widgetValue(requests);
      cards.push({
        id: requests.id,
        label: 'Demandes ouvertes',
        value: value ?? '-',
        sub: 'maintenance en cours',
        link: requests.link,
        color: 'warning',
        alert: typeof value === 'number' && value > 0,
        icon: 'wrench',
      });
    }

    const breakdown = pick('equipment.breakdown');
    if (breakdown) {
      const value = this._widgetValue(breakdown);
      cards.push({
        id: breakdown.id,
        label: 'Équipements en panne',
        value: value ?? '-',
        sub: 'intervention requise',
        link: breakdown.link,
        color: 'danger',
        alert: typeof value === 'number' && value > 0,
        icon: 'tool',
      });
    }

    const today = pick('agenda.today');
    if (today) {
      const value = this._widgetValue(today);
      cards.push({
        id: today.id,
        label: 'Présences aujourd’hui',
        value: value ?? '-',
        sub: 'inscriptions du jour',
        link: today.link,
        color: 'info',
        icon: 'calendar-days',
      });
    }

    return cards.slice(0, 5);
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

    const alerts = this._collectAlerts();
    const hero = this._heroCards();

    const grouped = {};
    for (const w of this.widgets) {
      if (!grouped[w.module]) grouped[w.module] = [];
      grouped[w.module].push(w);
    }
    const sortedModules = MODULE_ORDER.filter((m) => grouped[m]);

    modulesEl.innerHTML = `
      ${alerts.length ? this._alertsHtml(alerts) : ''}
      ${hero.length ? `
      <section class="dash-hero" aria-label="Indicateurs clés">
        ${hero.map((card) => this._heroCardHtml(card)).join('')}
      </section>` : ''}
      ${sortedModules.map((moduleCode) => {
        const meta = MODULE_META[moduleCode] || { label: moduleCode, icon: 'dashboard', color: 'primary', route: '' };
        const widgets = grouped[moduleCode];
        const heroIds = new Set(hero.map((h) => h.id));
        const excluded = new Set(SECTION_EXCLUDED[moduleCode] || []);
        const rest = widgets.filter((w) => !heroIds.has(w.id) && !excluded.has(w.id));
        if (!rest.length) return '';
        return `
        <section class="dash-section dash-section--${meta.color}" aria-label="${meta.label}">
          <header class="dash-section-header">
            <span class="dash-section-icon" aria-hidden="true">${this._getIcon(meta.icon)}</span>
            <h2 class="dash-section-title">${meta.label}</h2>
            ${meta.route ? `<a class="dash-section-link" href="${meta.route}" data-link>Ouvrir le module →</a>` : ''}
          </header>
          <div class="dash-grid">
            ${rest.map((w) => this._renderWidget(w)).join('')}
          </div>
        </section>`;
      }).join('')}
    `;

    this._bindWidgets();
  }

  _alertsHtml(alerts) {
    return `
      <section class="dash-alerts" aria-label="Points à surveiller">
        <div class="dash-alerts-title">
          <span class="dash-alerts-badge" aria-hidden="true">!</span>
          <span>À surveiller</span>
          <span class="dash-alerts-count">${alerts.length}</span>
        </div>
        <ul class="dash-alerts-list">
          ${alerts.map((a) => `
            <li><a class="dash-alert dash-alert--${a.severity}" href="${a.link}" data-link>${a.text}</a></li>
          `).join('')}
        </ul>
      </section>`;
  }

  _heroCardHtml(card) {
    return `
      <article class="dash-hero-card dash-hero-card--${card.color}${card.alert ? ' dash-hero-card--alert' : ''}"
               data-link="${card.link}" role="button" tabindex="0" aria-label="${card.label}">
        <div class="dash-hero-top">
          <span class="dash-hero-icon" aria-hidden="true">${this._getIcon(card.icon)}</span>
          <span class="dash-hero-label">${card.label}</span>
        </div>
        <div class="dash-hero-value">${card.value}</div>
        ${card.sub ? `<div class="dash-hero-sub">${card.sub}</div>` : ''}
        ${typeof card.progress === 'number' ? `
        <div class="dash-progress" role="progressbar" aria-valuenow="${card.progress}" aria-valuemin="0" aria-valuemax="100">
          <span class="dash-progress-bar dash-progress-bar--${card.color}" style="width:${Math.min(100, Math.max(0, card.progress))}%"></span>
        </div>` : ''}
      </article>`;
  }

  _renderWidget(widget) {
    const value = this._widgetValue(widget);
    const displayValue = formatValue(value, widget.id);

    const isAlert = widget.widget_type === 'alert';
    const alertActive = isAlert && typeof value === 'number' && value > 0;
    const progress = this._progressFor(widget, value);

    return `
      <article class="dash-card${alertActive ? ' dash-card--alert' : ''}"
               ${widget.link ? `data-link="${widget.link}"` : ''} role="${widget.link ? 'button' : 'article'}" ${widget.link ? 'tabindex="0"' : ''}>
        <div class="dash-card-top">
          <span class="dash-card-icon dash-card-icon--${this._moduleColor(widget)}" aria-hidden="true">${this._getIcon(widget.icon)}</span>
          ${alertActive ? '<span class="dash-card-flag" aria-hidden="true">!</span>' : ''}
        </div>
        <div class="dash-card-value">${displayValue}</div>
        <div class="dash-card-title">${widget.title}</div>
        <div class="dash-card-desc">${widget.description}</div>
        ${progress !== null ? `
        <div class="dash-progress" role="progressbar" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100">
          <span class="dash-progress-bar dash-progress-bar--${this._moduleColor(widget)}" style="width:${Math.min(100, Math.max(0, progress))}%"></span>
        </div>` : ''}
        ${widget.link ? `<a class="dash-card-link" href="${widget.link}" data-link>Détail →</a>` : ''}
      </article>`;
  }

  _progressFor(widget, value) {
    if (typeof value !== 'number') return null;
    if (widget.id === 'housing.occupancy_rate') return value;
    const data = this._widgetData(widget.id) || {};
    if (widget.id === 'equipment.breakdown' && data.total) return Math.round((value / data.total) * 100);
    if (widget.id === 'equipment.inactive' && data.total) return Math.round((value / data.total) * 100);
    if ((widget.id === 'housing.occupied' || widget.id === 'housing.free') && data.total) {
      return Math.round((value / data.total) * 100);
    }
    if (widget.id === 'housing.to_clean' && data.total) return Math.round((value / data.total) * 100);
    return null;
  }

  _moduleColor(widget) {
    const meta = MODULE_META[widget.module];
    return meta ? meta.color : 'primary';
  }

  _bindWidgets() {
    if (!this.element) return;
    this.element.querySelectorAll('[data-link]').forEach((el) => {
      if (el.tagName === 'A') return; // les liens sont gérés par le routeur (data-link)
      const go = (event) => {
        if (event.target.closest('a')) return;
        const route = el.dataset.link;
        if (route) this.router.navigate(route);
      };
      el.addEventListener('click', go);
      el.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          go(event);
        }
      });
    });
  }

  _getIcon(iconName) {
    const icons = {
      dashboard: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect></svg>',
      building: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect><path d="M9 22v-4h6v4"></path><path d="M8 6h.01"></path><path d="M16 6h.01"></path><path d="M12 6h.01"></path><path d="M12 10h.01"></path><path d="M12 14h.01"></path><path d="M16 10h.01"></path><path d="M16 14h.01"></path><path d="M8 10h.01"></path><path d="M8 14h.01"></path></svg>',
      home: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>',
      wrench: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-3.76 3.76a6 6 0 0 1-7.94-7.94l3.77 3.77a1 1 0 0 0 1.4 0l1.6-1.6a1 1 0 0 0 0-1.4l-3.77-3.77a6 6 0 0 1 7.94-7.94l-3.77 3.77z"></path></svg>',
      tool: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-3.76 3.76a6 6 0 0 1-7.94-7.94l3.77 3.77a1 1 0 0 0 1.4 0l1.6-1.6a1 1 0 0 0 0-1.4l-3.77-3.77a6 6 0 0 1 7.94-7.94l-3.77 3.77z"></path></svg>',
      sparkles: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0 1.275-1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275z"></path></svg>',
      users: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>',
      calendar: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>',
      'calendar-days': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line><circle cx="8" cy="14.5" r="0.75" fill="currentColor"></circle><circle cx="12" cy="14.5" r="0.75" fill="currentColor"></circle><circle cx="16" cy="14.5" r="0.75" fill="currentColor"></circle><circle cx="8" cy="18" r="0.75" fill="currentColor"></circle><circle cx="12" cy="18" r="0.75" fill="currentColor"></circle><circle cx="16" cy="18" r="0.75" fill="currentColor"></circle></svg>',
      clipboard: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect></svg>',
      run: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="13" cy="4" r="2"></circle><path d="M6 21l3-7 4 2 2-5 4 4"></path><path d="M9 14l-3-4 4-3 3 3 3-1"></path></svg>',
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
