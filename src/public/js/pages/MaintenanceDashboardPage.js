import { authStore } from '../stores/auth.js';
import { getMaintenanceDashboard } from '../services/maintenanceApi.js';

function formatDate(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  return d.toLocaleDateString('fr-FR');
}

function getStatusColor(status) {
  const colors = {
    open: '#f59e0b',
    in_progress: '#3b82f6',
    waiting_parts: '#8b5cf6',
    waiting_intervention: '#6366f1',
    completed: '#10b981',
    cancelled: '#ef4444',
    draft: '#6b7280',
    planned: '#06b6d4',
    overdue: '#dc2626',
  };
  return colors[status] || '#6b7280';
}

function getStatusLabel(status) {
  const labels = {
    open: 'Ouverte',
    in_progress: 'En cours',
    waiting_parts: 'Attente pièces',
    waiting_intervention: 'Attente intervention',
    completed: 'Clôturée',
    cancelled: 'Annulée',
    draft: 'Brouillon',
    planned: 'Planifiée',
    overdue: 'En retard',
  };
  return labels[status] || status;
}

function getPriorityColor(priority) {
  const colors = {
    low: '#10b981',
    medium: '#f59e0b',
    high: '#f97316',
    critical: '#ef4444',
  };
  return colors[priority] || '#6b7280';
}

function getPriorityLabel(priority) {
  const labels = {
    low: 'Basse',
    medium: 'Moyenne',
    high: 'Haute',
    critical: 'Critique',
  };
  return labels[priority] || priority;
}

export class MaintenanceDashboardPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.dashboard = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this._authUnsubscribe = authStore.subscribe(() => {
      if (this.element) this.loadData();
    });
  }

  async loadData() {
    try {
      this.dashboard = await getMaintenanceDashboard();
      this._renderDashboard();
    } catch (error) {
      console.error('Erreur chargement dashboard maintenance:', error);
    }
  }

  _renderDashboard() {
    if (!this.element || !this.dashboard) return;
    const d = this.dashboard;

    const statsContainer = this.element.querySelector('[data-stats]');
    if (statsContainer) {
      statsContainer.innerHTML = `
        <div class="stat-card">
          <div class="stat-value">${d.requests?.open || 0}</div>
          <div class="stat-label">Demandes ouvertes</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${d.requests?.in_progress || 0}</div>
          <div class="stat-label">En cours</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${d.requests?.overdue || 0}</div>
          <div class="stat-label">En retard</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${d.requests?.completed_month || 0}</div>
          <div class="stat-label">Clôturées ce mois</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${d.work_orders?.open || 0}</div>
          <div class="stat-label">OT ouverts</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${d.work_orders?.in_progress || 0}</div>
          <div class="stat-label">OT en cours</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${d.equipment?.total || 0}</div>
          <div class="stat-label">Équipements</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${d.equipment?.in_maintenance || 0}</div>
          <div class="stat-label">En maintenance</div>
        </div>
      `;
    }

    const byStatusContainer = this.element.querySelector('[data-by-status]');
    if (byStatusContainer && d.requests?.by_status) {
      byStatusContainer.innerHTML = d.requests.by_status.map(s => `
        <div class="status-row">
          <span class="status-dot" style="background:${getStatusColor(s.status)}"></span>
          <span class="status-name">${getStatusLabel(s.status)}</span>
          <span class="status-count">${s.count}</span>
        </div>
      `).join('');
    }

    const byPriorityContainer = this.element.querySelector('[data-by-priority]');
    if (byPriorityContainer && d.requests?.by_priority) {
      byPriorityContainer.innerHTML = d.requests.by_priority.map(p => `
        <div class="status-row">
          <span class="status-dot" style="background:${getPriorityColor(p.priority)}"></span>
          <span class="status-name">${getPriorityLabel(p.priority)}</span>
          <span class="status-count">${p.count}</span>
        </div>
      `).join('');
    }

    const recentContainer = this.element.querySelector('[data-recent-requests]');
    if (recentContainer && d.requests?.recent) {
      if (d.requests.recent.length === 0) {
        recentContainer.innerHTML = '<p class="empty-message">Aucune demande récente</p>';
      } else {
        recentContainer.innerHTML = `
          <table class="data-table">
            <thead>
              <tr>
                <th>Réf</th>
                <th>Titre</th>
                <th>Statut</th>
                <th>Priorité</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              ${d.requests.recent.map(r => `
                <tr>
                  <td><code>${r.reference || '-'}</code></td>
                  <td>${r.title}</td>
                  <td><span class="status-badge" style="background:${getStatusColor(r.status)}">${getStatusLabel(r.status)}</span></td>
                  <td><span class="priority-badge" style="background:${getPriorityColor(r.priority)}">${getPriorityLabel(r.priority)}</span></td>
                  <td>${formatDate(r.created_at)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }
    }

    const overdueContainer = this.element.querySelector('[data-overdue]');
    if (overdueContainer && d.preventive?.overdue) {
      if (d.preventive.overdue.length === 0) {
        overdueContainer.innerHTML = '<p class="empty-message">Aucune maintenance en retard</p>';
      } else {
        overdueContainer.innerHTML = `
          <table class="data-table">
            <thead>
              <tr>
                <th>Équipement</th>
                <th>Plan</th>
                <th>Échéance</th>
                <th>Retard (j)</th>
              </tr>
            </thead>
            <tbody>
              ${d.preventive.overdue.map(o => `
                <tr>
                  <td>${o.equipment_name || '-'}</td>
                  <td>${o.plan_name || '-'}</td>
                  <td>${formatDate(o.due_date)}</td>
                  <td><span class="overdue-badge">${o.days_overdue || '-'}</span></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Tableau de bord Maintenance</h1>
          <p class="page-subtitle">Vue d'ensemble des activités de maintenance</p>
        </div>
      </div>

      <div class="dashboard-stats" data-stats></div>

      <div class="dashboard-grid">
        <div class="dashboard-card">
          <h3>Demandes par statut</h3>
          <div data-by-status></div>
        </div>
        <div class="dashboard-card">
          <h3>Demandes par priorité</h3>
          <div data-by-priority></div>
        </div>
      </div>

      <div class="dashboard-section">
        <h3>Demandes récentes</h3>
        <div data-recent-requests></div>
      </div>

      <div class="dashboard-section">
        <h3>Maintenances préventives en retard</h3>
        <div data-overdue></div>
      </div>
    `;
    return this.element;
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createMaintenanceDashboardPage(router) {
  return new MaintenanceDashboardPage(router);
}
