import { getSportDashboard } from '../services/sportApi.js?v=2';

export class SportDashboardPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.data = null;
  }

  async initialize() {
    this.data = await getSportDashboard();
  }

  render() {
    const data = this.data || {};
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div><h1>Sport</h1><p class="page-subtitle">Suivi de vos activités course, trail et ultra.</p></div>
        <button class="btn btn-primary" data-action="activities">Voir les activités</button>
      </div>
      <div class="stats-grid">
        ${this._stat('Activités', data.activity_count || 0)}
        ${this._stat('Distance récente', `${((data.recent_distance_m || 0) / 1000).toFixed(1)} km`)}
        ${this._stat('Durée récente', this._formatDuration(data.recent_duration_seconds || 0))}
        ${this._stat('D+ récent', `${Math.round(data.recent_elevation_gain_m || 0)} m`)}
      </div>
      <div class="card" style="margin-top:20px;">
        <div class="card-header"><h2>Dernière activité</h2></div>
        <div class="card-body">${data.latest_activity ? this._activity(data.latest_activity) : '<p class="text-muted">Aucune activité enregistrée.</p>'}</div>
      </div>
    `;
    this.element.querySelector('[data-action="activities"]')?.addEventListener('click', () => this.router.navigate('/sport/activities'));
    return this.element;
  }

  _stat(label, value) { return `<div class="stat-card"><div class="stat-card-label">${label}</div><div class="stat-card-value">${value}</div></div>`; }
  _activity(activity) { return `<strong>${this._escape(activity.activity_name || activity.sport_type)}</strong><br><span class="text-muted">${new Date(activity.started_at).toLocaleString('fr-FR')} · ${((activity.distance_m || 0) / 1000).toFixed(2)} km · ${this._formatDuration(activity.duration_seconds || 0)}</span>`; }
  _formatDuration(seconds) { return `${Math.floor(seconds / 3600)}h ${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}min`; }
  _escape(value) { const el = document.createElement('div'); el.textContent = value || ''; return el.innerHTML; }
}

export function createSportDashboardPage(router) { return new SportDashboardPage(router); }
