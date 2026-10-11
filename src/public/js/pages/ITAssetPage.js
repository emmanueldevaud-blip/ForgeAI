import { Table } from '../components/Table.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import { authStore } from '../stores/auth.js';
import {
  listItAssets,
  getItAsset,
  createItAsset,
  updateItAsset,
  deleteItAsset,
  getAssetObservations,
  getAssetAlerts,
  acknowledgeAlert,
  resolveAlert,
  getAssetHistory,
  checkAsset,
  monitorAllAssets,
  listNetworkRanges,
  getNetworkRange,
  createNetworkRange,
  updateNetworkRange,
  deleteNetworkRange,
  scanNetworkRange,
  getDiscoveryLogs,
  discoverAllRanges
} from '../services/itAssetApi.js';

export class ITAssetPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentSection = 'list';
    this.assets = [];
    this.observations = [];
    this.alerts = [];
    this.networkRanges = [];
    this.loading = false;
    this.loadingAlerts = false;
    this.page = 1;
    this.pageSize = 20;
    this.search = '';
    this.assetTypeFilter = '';
    this.statusFilter = '';
    this.selectedAssetId = null;
    this.selectedAssetName = null;
    this.alertFilter = null;
    this.selectedRangeId = null;
    this.selectedRangeName = '';
    this.selectedRangeCidr = '';
    this.discoveryLogs = [];
    this.discoveryLastScan = null;
    this.confirmDialog = new ConfirmDialog();
    this.table = null;
    this.rangeTable = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'reference', label: 'Référence' },
        { key: 'name', label: 'Nom' },
        { key: 'asset_type', label: 'Type' },
        { key: 'ip_address', label: 'Adresse IP' },
        { key: 'mac_address', label: 'Adresse MAC' },
        { key: 'serial_number', label: 'Série' },
        { key: 'room_name', label: 'Salle' },
        { key: 'status', label: 'Statut', render: (v) => `<span class="status-badge ${(v || '').toLowerCase()}">${this._escape(v || '')}</span>` },
      ],
      actions: [
        { key: 'view', label: 'Détails', icon: 'eye', permission: 'it_asset.view' },
        { key: 'delete', label: 'Supprimer', icon: 'trash', permission: 'it_asset.delete', variant: 'danger' },
      ],
      getItemId: (item) => item.id,
      onAction: (action, item) => this._handleAction(action, item),
      onSort: () => {},
      emptyMessage: 'Aucun asset trouvé. Ajoutez un nouvel asset ou lancez une découverte réseau.',
    });

    this.rangeTable = new Table({
      columns: [
        { key: 'name', label: 'Nom' },
        { key: 'cidr', label: 'CIDR' },
        {
          key: 'is_active',
          label: 'Active',
          render: (v) => `<span class="status-badge ${v ? 'active' : 'inactive'}">${v ? 'Oui' : 'Non'}</span>`,
        },
        { key: 'last_scan', label: 'Dernier scan', render: (v) => this._escape(v || 'Jamais') },
      ],
      actions: [
        { key: 'scan', label: 'Scanner', icon: 'eye', permission: 'it_asset.manage_network_ranges' },
      ],
      getItemId: (item) => item.id,
      onAction: (action, item) => this._handleRangeAction(action, item),
      onSort: () => {},
      emptyMessage: 'Aucune plage réseau configurée.',
    });

    this._authUnsubscribe = authStore.subscribe(() => this._updateButtonVisibility());
  }

  async loadData() {
    await this._loadData();
    this.render();
  }

  destroy() {
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
    this.table = null;
    this.rangeTable = null;
  }

  async _loadData() {
    await this.loadAssets();
    await this.loadNetworkRanges();
  }

  async loadAssets() {
    this.loading = true;
    this.render();
    try {
      const params = { page: this.page, page_size: this.pageSize };
      if (this.search) params.search = this.search;
      if (this.assetTypeFilter) params.asset_type = this.assetTypeFilter;
      if (this.statusFilter) params.status = this.statusFilter;
      const data = await listItAssets(params);
      this.assets = data.items || [];
      this.page = data.page || this.page;
      this.pageSize = data.page_size || this.pageSize;
      this._renderTable();
    } catch (err) {
      console.error('Error loading assets:', err);
    } finally {
      this.loading = false;
      this.render();
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

  async loadAssetDetails(id) {
    this.loading = true;
    this.render();
    try {
      const [asset, observations, alerts] = await Promise.all([
        getItAsset(id),
        getAssetObservations(id, 10),
        getAssetAlerts(id, null)
      ]);
      this.selectedAssetId = asset.id;
      this.selectedAssetName = asset.name;
      this.assets = [asset];
      this.observations = observations.items || [];
      this.alerts = alerts.items || [];
    } catch (err) {
      console.error('Error loading asset details:', err);
    } finally {
      this.loading = false;
      this.render();
    }
  }

  _renderTable() {
    if (!this.table || !this.element) return;
    const container = this.element.querySelector('[data-table]');
    if (!container) return;
    this.table.setData({
      items: this.assets,
      page: this.page,
      pageSize: this.pageSize,
      total: this.assets.length,
      totalPages: Math.ceil(this.assets.length / this.pageSize) || 1,
    });
    container.innerHTML = '';
    container.appendChild(this.table.render());
  }

  _renderRangeTable() {
    if (!this.rangeTable || !this.element) return;
    const container = this.element.querySelector('[data-range-table]');
    if (!container) return;
    this.rangeTable.setData({
      items: this.networkRanges,
      page: 1,
      pageSize: this.networkRanges.length || 20,
      total: this.networkRanges.length,
      totalPages: 1,
    });
    container.innerHTML = '';
    container.appendChild(this.rangeTable.render());
  }

  _handleAction(action, item) {
    switch (action) {
      case 'view':
        this.currentSection = 'asset-detail';
        this.render();
        this.loadAssetDetails(item.id);
        break;
      case 'delete':
        this.confirmDialog.open({
          title: 'Supprimer l\'asset',
          message: `Êtes-vous sûr de vouloir supprimer l'asset "${item.name}" ?`,
          variant: 'danger',
          onConfirm: async () => {
            await deleteItAsset(item.id);
            await this.loadAssets();
          }
        });
        break;
    }
  }

  async _handleRangeAction(action, item) {
    if (action === 'scan') {
      this.loading = true;
      this.render();
      await scanNetworkRange(item.id);
      await this.loadNetworkRanges();
      this.discoveryLastScan = new Date().toLocaleString('fr-FR');
      try {
        const logs = await getDiscoveryLogs(item.id);
        this.discoveryLogs = logs.items || [];
      } catch (err) {
        console.error('Error loading discovery logs:', err);
      }
      this.loading = false;
      this.render();
    }
  }

  _updateButtonVisibility() {
    if (!this.element) return;
    const canCreate = authStore.hasPermission('it_asset.create');
    const canManageRanges = authStore.hasPermission('it_asset.manage_network_ranges');
    const createBtn = this.element.querySelector('[data-action="create-asset"]');
    const createRangeBtn = this.element.querySelector('[data-action="create-range"]');
    if (createBtn) createBtn.style.display = canCreate ? '' : 'none';
    if (createRangeBtn) createRangeBtn.style.display = canManageRanges ? '' : 'none';
  }

  render() {
    if (!this.element) {
      this.element = document.createElement('div');
      this.element.className = 'it-asset-page';
    }
    this.element.innerHTML = this._getHTML();
    this._bindEvents();
    this._updateButtonVisibility();
    this._renderTable();
    this._renderRangeTable();
    return this.element;
  }

  _getHTML() {
    const filterLabels = [];
    if (this.search) filterLabels.push(`Recherche: "${this._escape(this.search)}"`);
    if (this.assetTypeFilter) filterLabels.push(`Type: ${this._escape(this.assetTypeFilter)}`);
    if (this.statusFilter) filterLabels.push(`Statut: ${this._escape(this.statusFilter)}`);

    let content = '';
    switch (this.currentSection) {
      case 'list':
        content = this._renderListView(filterLabels);
        break;
      case 'discovery':
        content = this._renderDiscoveryView();
        break;
      case 'alerts':
        content = this._renderAlertsView();
        break;
      case 'network-ranges':
        content = this._renderNetworkRangesView();
        break;
      case 'asset-detail':
        content = this._renderAssetDetailView();
        break;
      case 'general':
        content = this._renderGeneralView(filterLabels);
        break;
      case 'hardware':
        content = this._renderHardwareView(filterLabels);
        break;
      case 'network':
        content = this._renderNetworkView(filterLabels);
        break;
      case 'system':
        content = this._renderSystemView(filterLabels);
        break;
      case 'user-domain':
        content = this._renderUserDomainView(filterLabels);
        break;
      case 'supervision':
        content = this._renderSupervisionView();
        break;
      case 'history':
        content = this._renderHistoryView();
        break;
    }

    return `
      <div class="page-header">
        <h1>Parc Informatique</h1>
        ${filterLabels.length > 0 ? `<p class="filter-bar">${filterLabels.join(' | ')}</p>` : ''}
      </div>
      <nav class="page-tabs">
        <button class="page-tab ${this.currentSection === 'list' ? 'active' : ''}" data-section="list">Liste</button>
        <button class="page-tab ${this.currentSection === 'discovery' ? 'active' : ''}" data-section="discovery">Découverte</button>
        <button class="page-tab ${this.currentSection === 'alerts' ? 'active' : ''}" data-section="alerts">Alertes</button>
        <button class="page-tab ${this.currentSection === 'network-ranges' ? 'active' : ''}" data-section="network-ranges">Plages réseau</button>
        <button class="page-tab ${this.currentSection === 'general' ? 'active' : ''}" data-section="general">Général</button>
        <button class="page-tab ${this.currentSection === 'hardware' ? 'active' : ''}" data-section="hardware">Matériel</button>
        <button class="page-tab ${this.currentSection === 'network' ? 'active' : ''}" data-section="network">Réseau</button>
        <button class="page-tab ${this.currentSection === 'system' ? 'active' : ''}" data-section="system">Système & logiciels</button>
        <button class="page-tab ${this.currentSection === 'user-domain' ? 'active' : ''}" data-section="user-domain">Utilisateur & domaine</button>
        <button class="page-tab ${this.currentSection === 'supervision' ? 'active' : ''}" data-section="supervision">Supervision</button>
        <button class="page-tab ${this.currentSection === 'history' ? 'active' : ''}" data-section="history">Historique</button>
      </nav>
      ${content}
    `;
  }

  _renderListView(filterLabels) {
    return `
      <div class="page-actions">
        <button class="btn btn-primary" data-action="create-asset" data-bs-toggle="modal" data-bs-target="#assetModal">Nouvel asset</button>
        <button class="btn btn-secondary" data-action="create-range" data-bs-toggle="modal" data-bs-target="#rangeModal">Nouvelle plage</button>
        <button class="btn btn-secondary" data-action="monitor-all">Surveiller tout</button>
      </div>
      <div class="search-bar">
        <input type="text" class="form-control" placeholder="Rechercher..." data-search value="${this._escape(this.search)}">
        <select class="form-control" data-asset-type-filter>
          <option value="">Tous les types</option>
          <option value="server" ${this.assetTypeFilter === 'server' ? 'selected' : ''}>Serveur</option>
          <option value="workstation" ${this.assetTypeFilter === 'workstation' ? 'selected' : ''}>Poste de travail</option>
          <option value="network" ${this.assetTypeFilter === 'network' ? 'selected' : ''}>Équipement réseau</option>
          <option value="printer" ${this.assetTypeFilter === 'printer' ? 'selected' : ''}>Imprimante</option>
          <option value="other" ${this.assetTypeFilter === 'other' ? 'selected' : ''}>Autre</option>
        </select>
        <select class="form-control" data-status-filter>
          <option value="">Tous les statuts</option>
          <option value="en_service" ${this.statusFilter === 'en_service' ? 'selected' : ''}>En service</option>
          <option value="hors_service" ${this.statusFilter === 'hors_service' ? 'selected' : ''}>Hors service</option>
          <option value="en_panne" ${this.statusFilter === 'en_panne' ? 'selected' : ''}>En panne</option>
          <option value="en_maintenance" ${this.statusFilter === 'en_maintenance' ? 'selected' : ''}>En maintenance</option>
        </select>
      </div>
      <div class="table-container" data-table></div>
      <div class="pagination">
        <button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Précédent</button>
        <span>Page ${this.page} / ${Math.ceil(this.assets.length / this.pageSize) || 1}</span>
        <button class="btn btn-secondary" data-page="next" ${this.page >= (Math.ceil(this.assets.length / this.pageSize) || 1) ? 'disabled' : ''}>Suivant</button>
      </div>
    `;
  }

  _renderDiscoveryView() {
    return `
      <div class="discovery-panel">
        <h3>Découverte réseau</h3>
        <p>Sélectionnez une plage réseau à scanner :</p>
        <div class="discovery-controls">
          <select class="form-control" data-range-select>
            <option value="">-- Sélectionner une plage --</option>
            ${this.networkRanges.map(range => `
              <option value="${range.id}" ${range.id === this.selectedRangeId ? 'selected' : ''}>${this._escape(range.name)} (${this._escape(range.cidr)})</option>
            `).join('')}
          </select>
          <button class="btn btn-primary" data-action="scan-range" ${!this.selectedRangeId ? 'disabled' : ''}>Scanner la plage</button>
          <button class="btn btn-secondary" data-action="discover-all" ${this.networkRanges.length === 0 ? 'disabled' : ''}>Scanner toutes les plages</button>
        </div>
        ${this.selectedRangeId ? `
          <div class="range-info">
            <h4>Plage ${this._escape(this.selectedRangeName)}</h4>
            <p>CIDR: ${this._escape(this.selectedRangeCidr)}</p>
            <p>Dernier scan: ${this._escape(this.discoveryLastScan || 'Jamais')}</p>
          </div>
          ${this.discoveryLogs.length > 0 ? `
            <div class="logs-list">
              <h4>Logs de découverte (${this.discoveryLogs.length})</h4>
              ${this.discoveryLogs.map(log => `
                <div class="log-entry">
                  <span class="${(log.status || '').toLowerCase()}">${this._escape(log.status)}</span>
                  <span>${this._escape(log.ip_address)}</span>
                  <span>${this._escape(log.mac_address || '')}</span>
                  <span>${this._escape(log.hostname || '')}</span>
                </div>
              `).join('')}
            </div>
          ` : `<p>Aucun log de découverte. Cliquez sur "Scanner la plage" pour commencer.</p>`}
        ` : ''}
      </div>
    `;
  }

  _renderAlertsView() {
    if (!this.selectedAssetId) {
      return `
        <p>Sélectionnez un asset dans la liste pour voir ses alertes.</p>
        <button class="btn btn-primary" data-section="list">Retour à la liste</button>
      `;
    }
    const filteredAlerts = this.alertFilter === null
      ? this.alerts
      : this.alerts.filter(a => a.resolved === this.alertFilter);

    return `
      <div class="alerts-panel">
        <h3>Alertes pour ${this._escape(this.selectedAssetName)}</h3>
        <div class="filter-bar">
          <button class="btn btn-tertiary ${this.alertFilter === null ? 'active' : ''}" data-alert-filter="all">Toutes</button>
          <button class="btn btn-tertiary ${this.alertFilter === false ? 'active' : ''}" data-alert-filter="unresolved">Non résolues</button>
          <button class="btn btn-tertiary ${this.alertFilter === true ? 'active' : ''}" data-alert-filter="resolved">Résolues</button>
        </div>
        ${this.loadingAlerts
          ? '<p class="loading">Chargement des alertes...</p>'
          : filteredAlerts.length === 0
            ? '<p>Aucune alerte pour cet asset.</p>'
            : `
              <div class="alerts-list">
                ${filteredAlerts.map(alert => `
                  <div class="alert-item ${alert.resolved ? 'resolved' : ''}">
                    <div class="alert-header">
                      <span class="alert-type">${this._escape(alert.type)}</span>
                      <span class="alert-severity ${this._escape(alert.severity)}">${this._escape(alert.severity)}</span>
                    </div>
                    <div class="alert-message">${this._escape(alert.message)}</div>
                    <div class="alert-timestamp">${new Date(alert.created_at).toLocaleString('fr-FR')}</div>
                    ${!alert.resolved ? `
                      <div class="alert-actions">
                        <button class="btn btn-icon btn-sm" data-action="resolve-alert" data-alert-id="${alert.id}" title="Résoudre">✓</button>
                        <button class="btn btn-icon btn-sm" data-action="acknowledge-alert" data-alert-id="${alert.id}" title="Acquitter">↑</button>
                      </div>
                    ` : ''}
                  </div>
                `).join('')}
              </div>
            `
        }
      </div>
      <button class="btn btn-primary" data-section="list">Retour à la liste</button>
    `;
  }

  _renderNetworkRangesView() {
    return `
      <div class="network-ranges-panel">
        <h3>Plages réseau</h3>
        <div class="table-container" data-range-table></div>
        <div class="page-actions">
          <button class="btn btn-primary" data-action="create-range" data-bs-toggle="modal" data-bs-target="#rangeModal">Nouvelle plage</button>
          <button class="btn btn-secondary" data-section="discovery">Nouvelle découverte</button>
        </div>
      </div>
    `;
  }

  _renderGeneralView(filterLabels) {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un asset dans la liste.</p>';
    }
    const asset = this.assets[0];
    return `
      <div class="general-panel">
        <h3>Général</h3>
        <dl class="asset-info">
          <dt>Référence</dt><dd>${this._escape(asset.reference || '')}</dd>
          <dt>Nom</dt><dd>${this._escape(asset.name || '')}</dd>
          <dt>Description</dt><dd>${this._escape(asset.description || '')}</dd>
          <dt>Type</dt><dd>${this._escape(asset.asset_type || '')}</dd>
          <dt>Dernière collecte</dt><dd>${this._assetLastCollection(asset)}</dd>
          <dt>Source de découverte</dt><dd>${this._escape(asset.discovery_source || 'manual')}</dd>
          <dt>Dernière actualisation</dt><dd>${this._assetLastSeen(asset)}</dd>
        </dl>
      </div>
    `;
  }

  _renderHardwareView(filterLabels) {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un asset dans la liste.</p>';
    }
    const asset = this.assets[0];
    return `
      <div class="hardware-panel">
        <h3>Matériel</h3>
        <dl class="asset-info">
          <dt>Fabricant</dt><dd>${this._escape(asset.manufacturer || '')}</dd>
          <dt>Modèle</dt><dd>${this._escape(asset.model || '')}</dd>
          <dt>Numéro de série</dt><dd>${this._escape(asset.serial_number || '')}</dd>
          <dt>Processeur</dt><dd>${this._escape(asset.cpu_name || '')} (${asset.cpu_cores || 0} cœurs)</dd>
          <dt>RAM</dt><dd>${asset.ram_total_mb !== undefined ? `${asset.ram_total_mb} Mo` : 'Non renseigné'} (${asset.ram_free_mb !== undefined ? `${asset.ram_free_mb} Mo libres` : 'Non renseigné'})</dd>
          <dt>Stockage</dt><dd>${asset.disk_total_mb !== undefined ? `${asset.disk_total_mb} Mo` : 'Non renseigné'} (${asset.disk_free_mb !== undefined ? `${asset.disk_free_mb} Mo libres` : 'Non renseigné'})</dd>
          <dt>BIOS</dt><dd>${this._escape(asset.bios_version || '')}</dd>
          <dt>Fabricant système</dt><dd>${this._escape(asset.manufacturer_system || '')}</dd>
        </dl>
      </div>
    `;
  }

  _renderNetworkView(filterLabels) {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un asset dans la liste.</p>';
    }
    const asset = this.assets[0];
    return `
      <div class="network-panel">
        <h3>Réseau</h3>
        <dl class="asset-info">
          <dt>Adresse IP</dt><dd>${this._escape(asset.ip_address || '')}</dd>
          <dt>Adresse MAC</dt><dd>${this._escape(asset.mac_address || '')}</dd>
          <dt>DNS</dt><dd>${this._escape(asset.dns_servers || '')}</dd>
          <dt>VLAN</dt><dd>${this._escape(asset.vlan_id || '')}</dd>
          <dt>Sous-réseau</dt><dd>${this._escape(asset.subnet || '')}</dd>
        </dl>
      </div>
    `;
  }

  _renderSystemView(filterLabels) {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un asset dans la liste.</p>';
    }
    const asset = this.assets[0];
    return `
      <div class="system-panel">
        <h3>Système & logiciels</h3>
        <dl class="asset-info">
          <dt>OS</dt><dd>${this._escape(asset.os || '')}</dd>
          <dt>Version OS</dt><dd>${this._escape(asset.os_version || '')}</dd>
          <dt>Build OS</dt><dd>${this._escape(asset.os_build || '')}</dd>
          <dt>Architecture</dt><dd>${this._escape(asset.os_architecture || '')}</dd>
          <dt>Services Windows essentiels</dt><dd>${this._escape(asset.windows_services || '')}</dd>
          <dt>Mises à jour</dt><dd>${this._escape(asset.update_status || '')}</dd>
        </dl>
      </div>
    `;
  }

  _renderUserDomainView(filterLabels) {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un asset dans la liste.</p>';
    }
    const asset = this.assets[0];
    return `
      <div class="user-domain-panel">
        <h3>Utilisateur & domaine</h3>
        <dl class="asset-info">
          <dt>Domaine</dt><dd>${this._escape(asset.domain || '')}</dt>
          <dt>Nom ordinateur AD</dt><dd>${this._escape(asset.computer_name_ad || '')}</dd>
          <dt>Unité organisationnelle</dt><dd>${this._escape(asset.organizational_unit || '')}</dd>
          <dt>Dernière activité AD</dt><dd>${this._assetLastAdActivity(asset)}</dd>
          <dt>Rejoint au domaine</dt><dd>${asset.is_domain_joined !== undefined ? (asset.is_domain_joined ? 'Oui' : 'Non') : 'Non renseigné'}</dt>
        </dl>
      </div>
    `;
  }

  _renderSupervisionView() {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un asset dans la liste.</p>';
    }
    const asset = this.assets[0];
    const lastCheck = asset.last_check ? new Date(asset.last_check).toLocaleString('fr-FR') : 'Jamais';
    const lastSeen = asset.last_seen ? new Date(asset.last_seen).toLocaleString('fr-FR') : 'Jamais';
    const statusClass = asset.status ? asset.status.toLowerCase() : 'unknown';
    return `
      <div class="supervision-panel">
        <h3>Supervision</h3>
        <dl class="asset-info">
          <dt>Dernier vérification</dt><dd>${this._escape(lastCheck)}</dd>
          <dt>Dernierseen</dt><dd>${this._escape(lastSeen)}</dd>
          <dt>Status</dt><dd><span class="status-badge ${statusClass}">${this._escape(asset.status || '')}</span></dd>
          <dt>Ping suivant dans</dt><dd>5 min</dd>
          <dt>Dernière collecte agent</dt><dd>${this._assetLastCollection(asset)}</dd>
        </dl>
      </div>
    `;
  }

  _renderHistoryView() {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un asset dans la liste.</p>';
    }
    const asset = this.assets[0];
    return `
      <div class="history-panel">
        <h3>Historique des collectes</h3>
        ${asset.observations && asset.observations.length > 0 ? `
          <div class="observations-list">
            ${asset.observations.slice(0, 10).map(obs => `
              <div class="observation-entry">
                <span class="${(obs.status || '').toLowerCase()}">${this._escape(obs.status || '')}</span>
                <span>à ${new Date(obs.checked_at).toLocaleString('fr-FR')}</span>
                <span>méthode: ${this._escape(obs.check_method || 'ping')}</span>
                ${obs.response_time_ms !== undefined ? `<span>temps: ${obs.response_time_ms} ms</span>` : ''}
              </div>
            `).join('')}
          </div>
        ` : '<p>Aucune observation de collecte.</p>'}
        ${asset.alerts && asset.alerts.length > 0 ? `
          <div class="alerts-list-small">
            <h4>Alertes récentes (${asset.alerts.length})</h4>
            ${asset.alerts.slice(0, 5).map(alert => `
              <div class="alert-small ${alert.resolved ? 'resolved' : ''}">
                <span>${this._escape(alert.type)}</span>
                <span>${this._escape(alert.severity)}</span>
                <span>${new Date(alert.created_at).toLocaleString('fr-FR')}</span>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </div>
    `;
  }

  _renderAssetDetailView() {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Asset non trouvé.</p>';
    }
    const asset = this.assets[0];
    return `
      <div class="asset-detail">
        <h3>${this._escape(asset.name)}</h3>
        <dl class="asset-info">
          <dt>Référence</dt><dd>${this._escape(asset.reference || '')}</dd>
          <dt>Type</dt><dd>${this._escape(asset.asset_type || '')}</dd>
          <dt>Adresse IP</dt><dd>${this._escape(asset.ip_address || '')}</dd>
          <dt>Adresse MAC</dt><dd>${this._escape(asset.mac_address || '')}</dd>
          <dt>Numéro de série</dt><dd>${this._escape(asset.serial_number || '')}</dd>
          <dt>Salle</dt><dd>${this._escape(asset.room_name || '')}</dd>
          <dt>Statut</dt><dd><span class="status-badge ${(asset.status || '').toLowerCase()}">${this._escape(asset.status || '')}</span></dd>
        </dl>
        <div class="asset-actions">
          <button class="btn btn-secondary" data-section="list">Retour à la liste</button>
          <button class="btn btn-primary" data-action="check-asset" data-asset-id="${asset.id}">Vérifier</button>
        </div>
      </div>
    `;
  }

  _bindEvents() {
    if (!this.element) return;

    this.element.querySelectorAll('[data-section]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.currentSection = btn.dataset.section;
        if (this.currentSection === 'list' && this.selectedAssetId) {
          this.selectedAssetId = null;
          this.selectedAssetName = null;
          this.loadAssets();
        } else {
          this.render();
        }
      });
    });

    const searchInput = this.element.querySelector('[data-search]');
    if (searchInput) {
      let debounce;
      searchInput.addEventListener('input', () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
          this.search = searchInput.value;
          this.page = 1;
          this.loadAssets();
        }, 300);
      });
    }

    const typeFilter = this.element.querySelector('[data-asset-type-filter]');
    if (typeFilter) {
      typeFilter.addEventListener('change', () => {
        this.assetTypeFilter = typeFilter.value;
        this.page = 1;
        this.loadAssets();
      });
    }

    const statusFilter = this.element.querySelector('[data-status-filter]');
    if (statusFilter) {
      statusFilter.addEventListener('change', () => {
        this.statusFilter = statusFilter.value;
        this.page = 1;
        this.loadAssets();
      });
    }

    const rangeSelect = this.element.querySelector('[data-range-select]');
    if (rangeSelect) {
      rangeSelect.addEventListener('change', () => {
        this.selectedRangeId = rangeSelect.value ? parseInt(rangeSelect.value) : null;
        const range = this.networkRanges.find(r => r.id === this.selectedRangeId);
        if (range) {
          this.selectedRangeName = range.name;
          this.selectedRangeCidr = range.cidr;
        }
        this.render();
      });
    }

    this.element.querySelectorAll('[data-action="scan-range"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (this.selectedRangeId) {
          this.loading = true;
          this.render();
          await scanNetworkRange(this.selectedRangeId);
          await this.loadNetworkRanges();
          this.discoveryLastScan = new Date().toLocaleString('fr-FR');
          const logs = await getDiscoveryLogs(this.selectedRangeId);
          this.discoveryLogs = logs.items || [];
          this.loading = false;
          this.render();
        }
      });
    });

    this.element.querySelectorAll('[data-action="discover-all"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        this.loading = true;
        this.render();
        await discoverAllRanges();
        await this.loadNetworkRanges();
        this.loading = false;
        this.render();
      });
    });

    this.element.querySelectorAll('[data-action="monitor-all"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        this.loading = true;
        this.render();
        await monitorAllAssets();
        await this.loadAssets();
        this.loading = false;
        this.render();
      });
    });

    this.element.querySelectorAll('[data-action="check-asset"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.assetId);
        this.loading = true;
        this.render();
        await checkAsset(id);
        await this.loadAssets();
        this.loading = false;
        this.render();
      });
    });

    this.element.querySelectorAll('[data-action="resolve-alert"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const alertId = parseInt(btn.dataset.alertId);
        await resolveAlert(this.selectedAssetId, alertId);
        const alerts = await getAssetAlerts(this.selectedAssetId, null);
        this.alerts = alerts.items || [];
        this.render();
      });
    });

    this.element.querySelectorAll('[data-action="acknowledge-alert"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const alertId = parseInt(btn.dataset.alertId);
        await acknowledgeAlert(this.selectedAssetId, alertId);
        const alerts = await getAssetAlerts(this.selectedAssetId, null);
        this.alerts = alerts.items || [];
        this.render();
      });
    });

    this.element.querySelectorAll('[data-alert-filter]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.alertFilter = btn.dataset.alertFilter === 'all' ? null : btn.dataset.alertFilter === 'resolved';
        this.render();
      });
    });

    this.element.querySelectorAll('[data-page]').forEach(btn => {
      btn.addEventListener('click', () => {
        const direction = btn.dataset.page;
        if (direction === 'prev' && this.page > 1) {
          this.page--;
          this.loadAssets();
        } else if (direction === 'next' && this.page < Math.ceil(this.assets.length / this.pageSize)) {
          this.page++;
          this.loadAssets();
        }
      });
    });
  }

  _escape(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }


  _assetLastCollection(asset) {
    return asset.last_collection ? new Date(asset.last_collection).toLocaleString('fr-FR') : 'Jamais';
  }

  _assetLastSeen(asset) {
    return asset.last_seen ? new Date(asset.last_seen).toLocaleString('fr-FR') : 'Jamais';
  }

  _assetLastAdActivity(asset) {
    return asset.last_ad_activity ? new Date(asset.last_ad_activity).toLocaleString('fr-FR') : 'Jamais';
  }
}

export function createITAssetPage(router) {
  return new ITAssetPage(router);
}
