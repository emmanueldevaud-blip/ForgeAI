import { authStore } from '../stores/auth.js';
import { getHousingDashboard } from '../services/housingApi.js';

function formatDate(d) { return d ? new Date(d).toLocaleDateString('fr-FR') : '-'; }

export class HousingDashboardPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.dashboard = null;
  }

  async initialize() {}

  async loadData() {
    try {
      this.dashboard = await getHousingDashboard();
      this._render();
    } catch (e) { console.error('Erreur dashboard hébergement:', e); }
  }

  _render() {
    if (!this.element || !this.dashboard) return;
    const d = this.dashboard;

    const stats = this.element.querySelector('[data-stats]');
    if (stats) {
      stats.innerHTML = `
        <div class="stat-card"><div class="stat-value">${d.total_housings}</div><div class="stat-label">Total hébergements</div></div>
        <div class="stat-card"><div class="stat-value">${d.occupied}</div><div class="stat-label">Occupés</div></div>
        <div class="stat-card"><div class="stat-value">${d.free}</div><div class="stat-label">Libres</div></div>
        <div class="stat-card"><div class="stat-value">${d.arrivals_today}</div><div class="stat-label">Arrivées aujourd'hui</div></div>
        <div class="stat-card"><div class="stat-value">${d.departures_today}</div><div class="stat-label">Départs aujourd'hui</div></div>
        <div class="stat-card"><div class="stat-value">${d.to_clean}</div><div class="stat-label">À nettoyer</div></div>
        <div class="stat-card"><div class="stat-value">${d.unavailabilities}</div><div class="stat-label">Indisponibles</div></div>
        <div class="stat-card"><div class="stat-value">${d.occupancy_rate}%</div><div class="stat-label">Taux occupation</div></div>
      `;
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Tableau de bord Hébergements</h1>
          <p class="page-subtitle">Vue d'ensemble des hébergements</p>
        </div>
      </div>
      <div class="dashboard-stats" data-stats></div>
    `;
    return this.element;
  }

  destroy() { if (this.element) this.element.remove(); this.element = null; }
}

export function createHousingDashboardPage(router) { return new HousingDashboardPage(router); }
