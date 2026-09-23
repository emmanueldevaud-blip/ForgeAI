import { listEquipmentTypes } from '../services/equipmentApi.js';
import { authStore } from '../stores/auth.js';

export class MaintenanceRefsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.equipmentTypes = [];
  }

  async initialize() {
    await this._loadEquipmentTypes();
  }

  async _loadEquipmentTypes() {
    try {
      const r = await listEquipmentTypes({ page_size: 1000, is_active: true });
      this.equipmentTypes = r.items || [];
    } catch (e) { this.equipmentTypes = []; }
  }

  async loadData() {
    await this._loadEquipmentTypes();
    this._renderTypes();
  }

  _renderTypes() {
    if (!this.element) return;
    const container = this.element.querySelector('[data-types-list]');
    if (!container) return;
    if (this.equipmentTypes.length === 0) {
      container.innerHTML = '<p class="empty-message">Aucun type d\'équipement</p>';
      return;
    }
    container.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>Code</th>
            <th>Nom</th>
            <th>Description</th>
            <th>Statut</th>
          </tr>
        </thead>
        <tbody>
          ${this.equipmentTypes.map(t => `
            <tr>
              <td><code>${t.code || '-'}</code></td>
              <td>${t.name}</td>
              <td>${t.description || '-'}</td>
              <td><span class="status-badge status-${t.is_active ? 'active' : 'inactive'}">${t.is_active ? 'Actif' : 'Inactif'}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content maintenance-page';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Référentiels Maintenance</h1>
          <p class="page-subtitle">Types d’équipements et données de référence</p>
        </div>
      </div>

      <div class="refs-section">
        <h3>Types d’équipements</h3>
        <p class="section-desc">Les types d’équipements sont gérés dans le module Équipements. <a href="/equipment/refs">Gérer les types</a></p>
        <div data-types-list></div>
      </div>
    `;
    return this.element;
  }

  destroy() {
    if (this.element) this.element.remove();
    this.element = null;
  }
}

export function createMaintenanceRefsPage(router) { return new MaintenanceRefsPage(router); }
