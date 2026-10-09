import { BasePage } from '../components/BasePage.js';
import { useState, useEffect } from '../modules/lit-element/lit-element.js';
import { listItAssets, getItAsset, createItAsset, updateItAsset, deleteItAsset, importItAssets, getAssetObservations, getAssetAlerts, acknowledgeAlert, resolveAlert, getAssetHistory, checkAsset, monitorAllAssets, listNetworkRanges, getNetworkRange, createNetworkRange, updateNetworkRange, deleteNetworkRange, scanNetworkRange, getDiscoveryLogs, discoverAllRanges } from '../services/itAssetApi.js';

export class ITAssetPage extends BasePage {
  constructor() {
    super();
    this.title = 'Parc Informatique';
    this.currentSection = 'list';
    this.assets = [];
    this.observations = [];
    this.alerts = [];
    this.alertResolved = null;
    this.networkRanges = [];
    this.loading = true;
    this.page = 1;
    this.pageSize = 20;
    this.search = '';
    this.assetTypeFilter = '';
    this.statusFilter = '';
  }

  async firstUpdated() {
    await this.loadAssets();
    await this.loadNetworkRanges();
  }

  async loadAssets() {
    this.loading = true;
    try {
      const data = await listItAssets({ page: this.page, page_size: this.pageSize, search: this.search });
      this.assets = data.items || [];
      this.page = data.page || this.page;
      this.pageSize = data.page_size || this.pageSize;
    } catch (err) {
      console.error('Error loading assets:', err);
    } finally {
      this.loading = false;
      this.requestUpdate();
    }
  }

  async loadNetworkRanges() {
    try {
      const data = await listNetworkRanges({ page: 1, page_size: 100 });
      this.networkRanges = data.items || [];
    } catch (err) {
      console.error('Error loading network ranges:', err);
    }
  }

  async deleteAsset(id) {
    if (confirm('Êtes-vous sûr de vouloir supprimer cet asset ?')) {
      await deleteItAsset(id);
      await this.loadAssets();
    }
  }

  async acknowledgeAlertClick(alertId) {
    if (await acknowledgeAlert(this.selectedAssetId, alertId)) {
      await this.loadAssets();
    }
  }

  async resolveAlertClick(alertId) {
    if (await resolveAlert(this.selectedAssetId, alertId)) {
      await this.loadAssets();
    }
  }

  async checkAssetClick(id) {
    await checkAsset(id);
    await this.loadAssets();
  }

  async updateFilter() {
    await this.loadAssets();
  }

  async gotoSection(section) {
    this.currentSection = section;
    await this.loadAssets();
  }

  render() {
    const filterLabels = [];
    if (this.search) filterLabels.push(`Recherche: "${this.search}"`);
    if (this.assetTypeFilter) filterLabels.push(`Type: ${this.assetTypeFilter}`);
    if (this.statusFilter) filterLabels.push(`Statut: ${this.statusFilter}`);

    const header = html`
      <h2>${this.title}</h2>
      ${filterLabels.length > 0 ? html`<p class="filter-bar">${filterLabels.join(' | ')}</p>` : ''}
    `;

    switch (this.currentSection) {
      case 'list': {
        return html`
          ${header}
          <div class="page-header">
            <button class="btn-primary" @click="${() => this.gotoSection('discovery')}">Découverte réseau</button>
            <button class="btn-secondary" @click="${() => this.gotoSection('alerts')}">Alertes</button>
            <button class="btn-secondary" @click="${() => this.gotoSection('network-ranges')}">Plages réseau</button>
          </div>
          
          ${this.loading 
            ? html`<p class="loading">Chargement...</p>`
            : html`
            <div class="table-responsive">
              <table>
                <thead>
                  <tr>
                    <th>Référence</th>
                    <th>Nom</th>
                    <th>Type</th>
                    <th>Adresse IP</th>
                    <th>Adresse MAC</th>
                    <th>Série</th>
                    <th>Salle</th>
                    <th>Statut</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  ${this.assets.map(asset => html`
                    <tr>
                      <td>${asset.reference || ''}</td>
                      <td>${asset.name || ''}</td>
                      <td>${asset.asset_type || ''}</td>
                      <td>${asset.ip_address || ''}</td>
                      <td>${asset.mac_address || ''}</td>
                      <td>${asset.serial_number || ''}</td>
                      <td>${asset.room_name || ''}</td>
                      <td>
                        <span class="status-badge ${asset.status.toLowerCase()}">
                          ${asset.status}
                        </span>
                      </td>
                      <td>
                        <button class="btn-icon" @click="${() => this.getItAsset(asset.id)}" title="Détails">👁</button>
                        <button class="btn-icon" @click="${() => this.deleteAsset(asset.id)}" title="Supprimer">🗑</button>
                      </td>
                    </tr>
                  `)}
                </tbody>
              </table>
            </div>
            ${this.assets.length === 0 ? html`<p class="empty-state">Aucun asset trouvé. Ajoutez un nouvel asset ou lancez une découverte réseau.</p>` : ''}
            <div class="pagination">
              <button class="btn-secondary" @click="${() => this.page > 1 ? this.loadAssetsWithPage(this.page - 1) : null}" ?disabled="${this.page <= 1}">Préc.</button>
              <span>Page ${this.page} de ${this.page || 1}</span>
              <button class="btn-secondary" @click="${() => this.loadAssetsWithPage(this.page + 1)}" ?disabled="${this.page >= (this.totalPages || 1)}">Suiv.</button>
            </div>
            `}
        `;
      }

      case 'discovery': {
        return html`
          ${header}
          <div class="discovery-panel">
            <h3>Découverte réseau</h3>
            <p>Sélectionnez une plage réseau à scanner :</p>
            <select @change="${(e) => this.onRangeSelect(e.target.value)}">
              <option value="">-- Sélectionner une plage --</option>
              ${this.networkRanges.map(range => html`
                <option value="${range.id}" ${range.id === this.selectedRangeId ? 'selected' : ''}>${range.name} (${range.cidr})</option>
              `)}
            </select>
            <button class="btn-primary" @click="${this.onScanClick}" ?disabled="${!this.selectedRangeId}">Scanner la plage</button>
            <button class="btn-secondary" @click="${discoverAllRanges}" ?disabled="${this.networkRanges.length === 0}">Scanner toutes les plages</button>
          </div>
          
          ${this.selectedRangeId ? html`
            <div class="range-info">
              <h4>Plage ${this.selectedRangeName}</h4>
              <p>CIDR: ${this.selectedRangeCidr}</p>
              <p>Dernier scan: ${this.discoveryLastScan || 'Jamais'}</p>
            </div>
            ${this.discoveryLogs.length > 0 ? html`
              <div class="logs-list">
                <h4>Logs de découverte (${this.discoveryLogs.length})</h4>
                ${this.discoveryLogs.map(log => html`
                  <div class="log-entry">
                    <span class="${log.status.toLowerCase()}">${log.status}</span>
                    <span>${log.ip_address}</span>
                    <span>${log.mac_address || ''}</span>
                    <span>${log.hostname || ''}</span>
                  </div>
                `)}
              </div>
            ` : html`<p>Aucun log de découverte. Cliquez sur "Scanner la plage" pour commencer.</p>`}
          ` : ''}
        `;
      }

      case 'alerts': {
        if (!this.selectedAssetId) {
          return html`
            ${header}
            <p>Sélectionnez un asset dans la liste pour voir ses alertes.</p>
            <button class="btn-primary" @click="${() => this.gotoSection('list')}">Retour à la liste</button>
          `;
        }
        return html`
          ${header}
          <div class="alerts-panel">
            <h3>Alertes pour ${this.selectedAssetName}</h3>
            <div class="filter-bar">
              <button class="btn-tertiary" @click="${() => this.alertFilter = null}">Toutes les alertes</button>
              <button class="btn-tertiary" @click="${() => this.alertFilter = false}">Non résolues</button>
              <button class="btn-tertiary" @click="${() => this.alertFilter = true}">Résolues</button>
            </div>
            
            ${this.loadingAlerts
              ? html`<p class="loading">Chargement des alertes...</p>`
              : this.alerts.length === 0
                ? html`<p>Aucune alerte pour cet asset.</p>`
                : html`
                <div class="alerts-list">
                  ${this.alerts.map(alert => html`
                    <div class="alert-item ${alert.resolved ? 'resolved' : ''}">
                      <div class="alert-header">
                        <span class="alert-type">${alert.type}</span>
                        <span class="alert-severity ${alert.severity}">${alert.severity}</span>
                      </div>
                      <div class="alert-message">${alert.message}</div>
                      <div class="alert-timestamp">${new Date(alert.created_at).toLocaleString()}</div>
                      ${!alert.resolved ? html`
                        <div class="alert-actions">
                          <button class="btn-icon" @click="${() => this.resolveAlertClick(alert.id)}" title="Résoudre">✓</button>
                          <button class="btn-icon" @click="${() => this.acknowledgeAlertClick(alert.id)}" title="Acquitter">↑</button>
                        </div>
                      ` : ''}
                    </div>
                  `)}
                </div>
                `}
          </div>
          <button class="btn-primary" @click="${() => this.gotoSection('list')}">Retour à la liste</button>
        `;
      }

      case 'network-ranges': {
        return html`
          ${header}
          <div class="network-ranges-panel">
            <h3>Plages réseau</h3>
            <div class="table-responsive">
              <table>
                <thead>
                  <tr>
                    <th>Nom</th>
                    <th>CIDR</th>
                    <th>Active</th>
                    <th>Dernier scan</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  ${this.networkRanges.map(range => html`
                    <tr>
                      <td>${range.name}</td>
                      <td>${range.cidr}</td>
                      <td><span class="status-badge ${range.is_active ? 'active' : 'inactive'}">${range.is_active ? 'Oui' : 'Non'}</span></td>
                      <td>${range.last_scan || 'Jamais'}</td>
                      <td>
                        <button class="btn-icon" @click="${() => this.scanNetworkRange(range.id)}" title="Scanner">🔍</button>
                        <button class="btn-icon" @click="${() => this.getNetworkRange(range.id)}" title="Détails">ℹ</button>
                      </td>
                    </tr>
                  `)}
                </tbody>
              </table>
            </div>
            <div>
              <button class="btn-primary" @click="${() => this.gotoSection('discovery')}">Nouvelle découverte</button>
            </div>
          </div>
        `;
      }
    }
  }

  // Internal methods
  async loadAssetsWithPage(page) {
    this.page = page;
    await this.loadAssets();
  }

  async onRangeSelect(rangeId) {
    this.selectedRangeId = rangeId;
    const range = this.networkRanges.find(r => r.id === rangeId);
    if (range) {
      this.selectedRangeName = range.name;
      this.selectedRangeCidr = range.cidr;
    }
  }

  async onScanClick() {
    if (this.selectedRangeId) {
      await scanNetworkRange(this.selectedRangeId);
      await this.loadNetworkRanges();
    }
  }

  // Getters for selected asset
  get selectedAssetId() {
    // This would be set when viewing asset details
    return this._selectedAssetId;
  }
  set selectedAssetId(id) {
    this._selectedAssetId = id;
    if (id) {
      this.loadAssetDetails(id);
    }
  }

  async loadAssetDetails(id) {
    this.loading = true;
    try {
      const [asset, observations, alerts] = await Promise.all([
        getItAsset(id),
        getAssetObservations(id, 10),
        getAssetAlerts(id, null)
      ]);
      this.assets = [asset];
      this.observations = observations.items || [];
      this.alerts = alerts.items || [];
      this.alertResolved = alerts.resolved || null;
    } catch (err) {
      console.error('Error loading asset details:', err);
    } finally {
      this.loading = false;
      this.requestUpdate();
    }
  }
}

customElements.define('it-asset-page', ITAssetPage);