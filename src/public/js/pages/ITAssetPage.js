import { Table } from '../components/Table.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';
import { authStore } from '../stores/auth.js';
import { listRooms } from '../services/buildingsApi.js';
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
  discoverAllRanges,
  setManagementUrl,
  detectManagementUrl,
  checkManagementUrl
} from '../services/itAssetApi.js?v=2';

const ASSET_TYPES = [
  { value: 'pc_windows', label: 'Poste Windows' },
  { value: 'pc_linux', label: 'Poste Linux' },
  { value: 'server', label: 'Serveur' },
  { value: 'printer', label: 'Imprimante' },
  { value: 'switch', label: 'Commutateur' },
  { value: 'router', label: 'Routeur' },
  { value: 'firewall', label: 'Pare-feu' },
  { value: 'access_point', label: "Point d'accès" },
  { value: 'other', label: 'Autre' },
];

const ASSET_STATUSES = [
  { value: 'online', label: 'En ligne' },
  { value: 'offline', label: 'Hors ligne' },
  { value: 'degraded', label: 'Dégradé' },
  { value: 'unknown', label: 'Inconnu' },
  { value: 'maintenance', label: 'En maintenance' },
];

const ASSET_STATUS_LABELS = Object.fromEntries(ASSET_STATUSES.map(({ value, label }) => [value, label]));

const ASSET_TYPE_LABELS = Object.fromEntries(ASSET_TYPES.map(({ value, label }) => [value, label]));

// États de l'interface web d'administration (management_url_status)
const MGMT_STATUS_LABELS = {
  accessible: 'Accessible',
  auth_required: 'Authentification requise',
  unreachable: 'Indisponible',
  tls_untrusted: 'Certificat non fiable',
  to_check: 'À vérifier',
};

const MGMT_STATUS_BADGES = {
  accessible: 'badge-success',
  auth_required: 'badge-warning',
  unreachable: 'badge-danger',
  tls_untrusted: 'badge-warning',
  to_check: 'badge-muted',
};

const SECTION_ROUTES = {
  list: '/it-assets',
  discovery: '/it-assets/discovery',
  alerts: '/it-assets/alerts',
  'network-ranges': '/it-assets/network-ranges',
};

export class ITAssetPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.currentSection = 'list';
    this.assets = [];
    this.observations = [];
    this.alerts = [];
    this.networkRanges = [];
    this.rangeSearch = '';
    this.rooms = [];
    this.loading = false;
    this.loadingAlerts = false;
    this.page = 1;
    this.pageSize = 20;
    this.total = 0;
    this.search = '';
    this.assetTypeFilter = '';
    this.statusFilter = '';
    this.sortBy = 'created_at';
    this.sortOrder = 'desc';
    this.selectedAssetId = null;
    this.selectedAssetName = null;
    this.alertFilter = null;
    this.selectedRangeId = null;
    this.selectedRangeName = '';
    this.selectedRangeCidr = '';
    this.discoveryLogs = [];
    this.discoveryLastScan = null;
    this.activeScan = null;
    this.monitoringSummary = '';
    this._scanPollTimer = null;
    this.confirmDialog = new ConfirmDialog();
    this.table = null;
    this.rangeTable = null;
    this._authUnsubscribe = null;
  }

  async initialize() {
    this.table = new Table({
      columns: [
        { key: 'reference', label: 'Référence', sortable: true },
        {
          key: 'name',
          label: 'Nom',
          sortable: true,
          render: (item) => {
            const name = this._escape(String(item.name || '').toUpperCase());
            const url = String(item.management_url || '');
            const safeUrl = /^https?:\/\//i.test(url) ? url : '';
            if (!safeUrl) return name;
            return `<a href="${this._escapeAttr(safeUrl)}" target="_blank" rel="noopener noreferrer" title="Ouvrir l'interface d'administration">${name}</a>`;
          },
        },
        { key: 'asset_type', label: 'Type', sortable: true, render: (item) => this._escape(ASSET_TYPE_LABELS[item.asset_type] || item.asset_type || '') },
        { key: 'ip_address', label: 'Adresse IP', sortable: true },
        { key: 'mac_address', label: 'Adresse MAC', sortable: true },
        { key: 'room_name', label: 'Local', render: (item) => this._escape(item.room?.name || 'Non renseigné') },
        { key: 'status', label: 'Statut', sortable: true, render: (item) => this._renderStatus(item.status) },
      ],
      actions: [
        { key: 'edit', label: 'Modifier', icon: 'edit', permission: 'it_asset.update' },
        { key: 'view', label: 'Détails', icon: 'eye', permission: 'it_asset.view' },
        { key: 'delete', label: 'Supprimer', icon: 'trash', permission: 'it_asset.delete', variant: 'danger' },
      ],
      getItemId: (item) => item.id,
      onAction: (action, item) => this._handleAction(action, item),
      onSort: (sortKey, sortDirection) => this._sortAssets(sortKey, sortDirection),
      emptyMessage: 'Aucun équipement trouvé. Ajoutez un nouvel équipement ou lancez un scan réseau.',
    });

    this.rangeTable = new Table({
      columns: [
        { key: 'name', label: 'Nom' },
        { key: 'cidr', label: 'CIDR' },
        {
          key: 'room',
          label: 'Local',
          render: (item) => {
            if (item.room) return this._escape(`${item.room.reference} — ${item.room.name}`);
            if (item.room_id) {
              const r = this.rooms.find(rm => rm.id === item.room_id);
              if (r) return this._escape(`${r.reference} — ${r.name}`);
            }
            return 'Non renseigné';
          },
        },
        {
          key: 'is_active',
          label: 'Active',
          render: (item) => `<span class="status-badge ${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Oui' : 'Non'}</span>`,
        },
        { key: 'last_scan_at', label: 'Dernier scan', render: (item) => this._escape(item.last_scan_at || 'Jamais') },
      ],
      actions: [
        { key: 'edit', label: 'Modifier', icon: 'edit', permission: 'it_asset.manage_network_ranges' },
        { key: 'scan', label: 'Scanner', icon: 'eye', permission: 'it_asset.manage_network_ranges' },
      ],
      getItemId: (item) => item.id,
      onAction: (action, item) => this._handleRangeAction(action, item),
      onSort: () => {},
      emptyMessage: 'Aucune plage réseau configurée.',
    });

    this._authUnsubscribe = authStore.subscribe(() => this._updateButtonVisibility());
  }

  _renderStatus(status) {
    const value = String(status || 'unknown').toLowerCase();
    const label = ASSET_STATUS_LABELS[value] || 'Inconnu';
    return `<span class="asset-status status-badge ${this._escape(value)}"><span class="asset-status-dot" aria-hidden="true"></span>${this._escape(label)}</span>`;
  }

  async _sortAssets(sortKey, sortDirection) {
    this.sortBy = sortKey;
    this.sortOrder = sortDirection;
    this.page = 1;
    await this.loadAssets();
  }

  async loadData() {
    await this._loadData();
    this.render();
  }

  setSection(section) {
    this.currentSection = section;
    if (section === 'list' && this.selectedAssetId) {
      this.selectedAssetId = null;
      this.selectedAssetName = null;
    }
  }

  destroy() {
    this._stopScanPolling();
    this._authUnsubscribe?.();
    if (this.element) this.element.remove();
    this.element = null;
    this.table = null;
    this.rangeTable = null;
  }

  async _loadData() {
    await this.loadAssets();
    await this.loadNetworkRanges();
    await this.loadRooms();
  }

  async loadRooms() {
    if (this.rooms.length > 0) return;
    try {
      const data = await listRooms({ is_active: true, page_size: 1000, sort_by: 'reference', sort_order: 'asc' });
      this.rooms = data.items || [];
    } catch (err) {
      console.error('Error loading rooms:', err);
    }
  }

  async loadAssets() {
    this.loading = true;
    this.render();
    try {
      const params = { page: this.page, page_size: this.pageSize };
      if (this.search) params.search = this.search;
      if (this.assetTypeFilter) params.asset_type = this.assetTypeFilter;
      if (this.statusFilter) params.status = this.statusFilter;
      params.sort_by = this.sortBy;
      params.sort_order = this.sortOrder;
      const data = await listItAssets(params);
      this.assets = data.items || [];
      this.total = data.total || 0;
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
      this.alerts = Array.isArray(alerts) ? alerts : (alerts.items || []);
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
      sortBy: this.sortBy,
      sortOrder: this.sortOrder,
      total: this.total,
      totalPages: Math.ceil(this.total / this.pageSize) || 1,
    });
    container.innerHTML = '';
    container.appendChild(this.table.render());
  }

  _renderRangeTable() {
    if (!this.rangeTable || !this.element) return;
    const container = this.element.querySelector('[data-range-table]');
    if (!container) return;
    const query = this.rangeSearch.trim().toLowerCase();
    const ranges = query ? this.networkRanges.filter(range => `${range.name || ''} ${range.cidr || ''}`.toLowerCase().includes(query)) : this.networkRanges;
    this.rangeTable.setData({
      items: ranges,
      page: 1,
      pageSize: this.networkRanges.length || 20,
      total: ranges.length,
      totalPages: 1,
    });
    container.innerHTML = '';
    container.appendChild(this.rangeTable.render());
  }

  _handleAction(action, item) {
    switch (action) {
      case 'edit':
        this._showAssetModal(item);
        break;
      case 'view':
        this._showAssetInfoModal(item);
        break;
      case 'delete':
        this.confirmDialog.open({
          title: 'Supprimer l\'équipement',
          message: `Êtes-vous sûr de vouloir supprimer l'équipement "${item.name}" ?`,
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
    if (action === 'edit') {
      this._showRangeModal(item);
      return;
    }
    if (action === 'scan') {
      await this._startScan(item.id);
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
      this.element.className = 'page-content housing-page it-asset-page';
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
    if (this.assetTypeFilter) filterLabels.push(`Type: ${this._escape(ASSET_TYPE_LABELS[this.assetTypeFilter] || this.assetTypeFilter)}`);
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
      <nav class="admin-tabs" role="tablist" aria-label="Sections du parc informatique">
        <button class="admin-tab" role="tab" data-section="list" aria-selected="${this.currentSection === 'list'}">Liste</button>
        <button class="admin-tab" role="tab" data-section="network-ranges" aria-selected="${this.currentSection === 'network-ranges'}">Plages réseau</button>
      </nav>
      ${content}
    `;
  }

  _renderListView(filterLabels) {
    return `
      <div class="page-filters">
        <div class="filter-group"><label class="sr-only" for="it-asset-search">Rechercher</label><input id="it-asset-search" type="text" class="form-input" placeholder="Rechercher..." data-search value="${this._escape(this.search)}"></div>
        <div class="filter-group"><label class="sr-only" for="it-asset-type-filter">Filtrer par type</label><select id="it-asset-type-filter" class="form-select" data-asset-type-filter>
          <option value="">Tous les types</option>
          ${ASSET_TYPES.map(type => `<option value="${type.value}" ${this.assetTypeFilter === type.value ? 'selected' : ''}>${type.label}</option>`).join('')}
        </select></div>
        <div class="filter-group"><label class="sr-only" for="it-asset-status-filter">Filtrer par statut</label><select id="it-asset-status-filter" class="form-select" data-status-filter>
          <option value="">Tous les statuts</option>
          ${ASSET_STATUSES.map(status => `<option value="${status.value}" ${this.statusFilter === status.value ? 'selected' : ''}>${status.label}</option>`).join('')}
        </select></div>
        <div style="display:flex;align-items:center;gap:var(--spacing-2);margin-left:auto;">
          <button class="btn btn-secondary" data-action="monitor-all" ${this.loading ? 'disabled' : ''}>${this.loading ? 'Actualisation en cours…' : 'Actualiser tout'}</button>
          <button class="btn btn-primary" data-action="create-asset">Nouvel équipement</button>
        </div>
      </div>
      <div class="page-info"><span>${this.total} équipement${this.total > 1 ? 's' : ''}</span></div>
      ${this.monitoringSummary ? `<div class="it-monitoring-summary" role="status">${this._escape(this.monitoringSummary)}</div>` : ''}
      <div data-table></div>
      <div class="pagination">
        <button class="btn btn-secondary" data-page="prev" ${this.page <= 1 ? 'disabled' : ''}>Précédent</button>
        <span>Page ${this.page} / ${Math.ceil(this.total / this.pageSize) || 1}</span>
        <button class="btn btn-secondary" data-page="next" ${this.page >= (Math.ceil(this.total / this.pageSize) || 1) ? 'disabled' : ''}>Suivant</button>
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
          <button class="btn btn-primary" data-action="scan-range" ${!this.selectedRangeId || this.activeScan ? 'disabled' : ''}>${this.activeScan ? 'Scan en cours…' : 'Scanner la plage'}</button>
          <button class="btn btn-secondary" data-action="discover-all" ${this.networkRanges.length === 0 || this.activeScan ? 'disabled' : ''}>Scanner toutes les plages</button>
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
                  <span>${new Date(log.started_at).toLocaleString('fr-FR')}</span>
                  <span>${log.hosts_scanned} scannés</span>
                  <span>${log.hosts_found} trouvés</span>
                  <span>+${log.assets_created} / ~${log.assets_updated}</span>
                  ${log.errors ? `<span class="log-error">${this._escape(log.errors)}</span>` : ''}
                </div>
              `).join('')}
            </div>
          ` : `<p>Aucun log de découverte. Cliquez sur "Scanner la plage" pour commencer.</p>`}
        ` : ''}
      </div>
    `;
  }

  // ============================================================
  // SUIVI DE SCAN EN DIRECT
  // ============================================================

  _scanProgressHtml() {
    if (!this.activeScan || this.activeScan.length === 0) return '';
    const items = this.activeScan.map((s) => {
      const total = s.totalHosts || 0;
      const pct = total > 0 ? Math.min(100, Math.round((s.hosts_scanned / total) * 100)) : null;
      const stats = `${s.hosts_scanned}${total ? ' / ' + total : ''} hôte(s) scanné(s)`
        + ` — ${s.hosts_found} en ligne`
        + ` — +${s.assets_created} créé(s), ~${s.assets_updated} mis à jour`;
      const statusLabel = s.status === 'success'
        ? '<span class="scan-status scan-status-success">Terminé</span>'
        : s.status === 'failed'
          ? '<span class="scan-status scan-status-failed">Échec</span>'
          : '<span class="scan-status scan-status-running">En cours…</span>';
      return `
        <div class="scan-progress-item">
          <div class="scan-progress-header">
            <span class="scan-progress-name">${this._escape(s.rangeName)}</span>
            ${statusLabel}
          </div>
          <div class="scan-progress-stats">${this._escape(stats)}</div>
          <div class="scan-progress-bar">
            <div class="scan-progress-fill ${pct === null ? 'scan-progress-fill-indeterminate' : ''}" style="width: ${pct === null ? 30 : pct}%"></div>
          </div>
          ${s.errors ? `<div class="scan-progress-error">${this._escape(s.errors)}</div>` : ''}
        </div>
      `;
    }).join('');
    return `<div class="scan-progress">${items}</div>`;
  }

  _updateScanProgressDom() {
    const container = this.element?.querySelector('[data-scan-progress]');
    if (container) container.innerHTML = this._scanProgressHtml();
  }

  async _startScan(rangeId = null) {
    if (this.activeScan) return;
    try {
      let scans;
      if (rangeId) {
        const res = await scanNetworkRange(rangeId);
        scans = [{ range_id: rangeId, log_id: res.log_id, total_hosts: res.total_hosts }];
      } else {
        const res = await discoverAllRanges();
        scans = res.scans || [];
      }
      if (!scans.length) {
        console.warn('Aucune plage active à scanner');
        return;
      }
      this.activeScan = scans.map((s) => ({
        rangeId: s.range_id,
        logId: s.log_id,
        totalHosts: s.total_hosts || 0,
        rangeName: (this.networkRanges.find((r) => r.id === s.range_id) || {}).name || `Plage ${s.range_id}`,
        status: 'running',
        hosts_scanned: 0,
        hosts_found: 0,
        assets_created: 0,
        assets_updated: 0,
        errors: null,
      }));
      this.render();
      this._startScanPolling();
    } catch (err) {
      console.error('Impossible de démarrer le scan:', err);
      this.activeScan = null;
    }
  }

  _startScanPolling() {
    this._stopScanPolling();
    this._scanPollTimer = setInterval(() => this._pollScan(), 1500);
    this._pollScan();
  }

  _stopScanPolling() {
    if (this._scanPollTimer) {
      clearInterval(this._scanPollTimer);
      this._scanPollTimer = null;
    }
  }

  async _pollScan() {
    if (!this.activeScan || this.activeScan.length === 0) {
      this._stopScanPolling();
      return;
    }
    let allDone = true;
    for (const entry of this.activeScan) {
      if (entry.status !== 'running') continue;
      try {
        const logs = await getDiscoveryLogs(entry.rangeId);
        const list = Array.isArray(logs) ? logs : (logs.items || []);
        const log = list.find((l) => l.id === entry.logId);
        if (log) {
          entry.status = (log.status || 'running').toLowerCase();
          entry.hosts_scanned = log.hosts_scanned || 0;
          entry.hosts_found = log.hosts_found || 0;
          entry.assets_created = log.assets_created || 0;
          entry.assets_updated = log.assets_updated || 0;
          entry.errors = log.errors || null;
          if (!entry.totalHosts && log.details && log.details.total_hosts) {
            entry.totalHosts = log.details.total_hosts;
          }
        }
      } catch (err) {
        console.error('Polling scan:', err);
      }
      if (entry.status === 'running') allDone = false;
    }
    if (allDone) {
      this._stopScanPolling();
      const summary = this.activeScan
        .map((s) => `${s.rangeName}: ${s.status === 'success' ? 'terminé' : 'échec'} (${s.hosts_found} en ligne, +${s.assets_created}/~${s.assets_updated})`)
        .join(' | ');
      console.info('Scan terminé —', summary);
      this.activeScan = null;
      this.discoveryLastScan = new Date().toLocaleString('fr-FR');
      await this.loadNetworkRanges();
      await this.loadAssets();
      if (this.selectedRangeId) {
        try {
          const logs = await getDiscoveryLogs(this.selectedRangeId);
          this.discoveryLogs = Array.isArray(logs) ? logs : (logs.items || []);
        } catch (err) {
          console.error('Error loading discovery logs:', err);
        }
      }
      this.render();
    } else {
      this._updateScanProgressDom();
    }
  }

  _renderAlertsView() {
    if (!this.selectedAssetId) {
      return `
        <p>Sélectionnez un équipement dans la liste pour voir ses alertes.</p>
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
            ? '<p>Aucune alerte pour cet équipement.</p>'
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
        <div class="page-filters">
          <input type="search" class="form-input" style="width:min(100%, 320px);" placeholder="Rechercher une plage..." data-range-search value="${this._escape(this.rangeSearch)}">
          <div style="display:flex;align-items:center;gap:var(--spacing-2);margin-left:auto;">
            <button class="btn btn-secondary" data-action="discover-all" ${this.networkRanges.length === 0 || this.activeScan ? 'disabled' : ''}>Scanner toutes les plages</button>
            <button class="btn btn-primary" data-action="create-range">Nouvelle plage</button>
          </div>
        </div>
        <div class="table-container" data-range-table></div>
        <div data-scan-progress>${this._scanProgressHtml()}</div>
      </div>
    `;
  }

  _renderGeneralView(filterLabels) {
    if (!this.selectedAssetId || this.assets.length === 0) {
      return '<p>Sélectionnez un équipement dans la liste.</p>';
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
      return '<p>Sélectionnez un équipement dans la liste.</p>';
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
      return '<p>Sélectionnez un équipement dans la liste.</p>';
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
      return '<p>Sélectionnez un équipement dans la liste.</p>';
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
      return '<p>Sélectionnez un équipement dans la liste.</p>';
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
      return '<p>Sélectionnez un équipement dans la liste.</p>';
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
      return '<p>Sélectionnez un équipement dans la liste.</p>';
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
          ${authStore.hasPermission('it_asset.update') ? `<button class="btn btn-secondary" data-action="edit-asset" data-asset-id="${asset.id}">Modifier</button>` : ''}
          <button class="btn btn-primary" data-action="check-asset" data-asset-id="${asset.id}">Vérifier</button>
        </div>
      </div>
    `;
  }

  // Section « Interface d'administration » de la fiche équipement :
  // URL + protocole, état, dernière vérification, ouverture de l'interface et
  // actions (saisie manuelle, test, recherche) selon les permissions existantes.
  _fillManagementSection(container, asset) {
    if (!container || !asset) return;
    const url = String(asset.management_url || '');
    // Seules les URL http/https sont affichées et ouvrables (défense en
    // profondeur : le backend valide déjà le schéma à la saisie).
    const safeUrl = /^https?:\/\//i.test(url) ? url : '';
    let protocol = '-';
    if (safeUrl) {
      try { protocol = new URL(safeUrl).protocol.replace(':', ''); } catch (err) { protocol = '-'; }
    }
    const status = String(asset.management_url_status || 'to_check').toLowerCase();
    const statusLabel = MGMT_STATUS_LABELS[status] || MGMT_STATUS_LABELS.to_check;
    const badge = MGMT_STATUS_BADGES[status] || MGMT_STATUS_BADGES.to_check;
    const source = asset.management_url_source === 'manual' ? 'Saisie manuelle'
      : asset.management_url_source === 'auto' ? 'Détection automatique' : '-';
    const checkedAt = asset.management_url_detected_at
      ? new Date(asset.management_url_detected_at).toLocaleString('fr-FR') : '-';
    const canUpdate = authStore.hasPermission('it_asset.update');
    const canDiscover = authStore.hasPermission('it_asset.manage_discovery');

    container.innerHTML = `
      <dl class="asset-info">
        <div class="asset-info-row"><dt>URL</dt><dd>${url ? this._escape(url) : 'Aucune interface détectée'}</dd></div>
        <div class="asset-info-row"><dt>Protocole</dt><dd>${this._escape(protocol)}</dd></div>
        <div class="asset-info-row"><dt>État</dt><dd><span class="status-badge ${badge}">${this._escape(statusLabel)}</span></dd></div>
        <div class="asset-info-row"><dt>Dernière vérification</dt><dd>${this._escape(checkedAt)}</dd></div>
        <div class="asset-info-row"><dt>Source</dt><dd>${this._escape(source)}</dd></div>
      </dl>
      <div class="asset-actions">
        ${safeUrl ? `<a class="btn btn-primary" href="${this._escapeAttr(safeUrl)}" target="_blank" rel="noopener noreferrer">Ouvrir l'interface</a>` : ''}
        ${canDiscover ? '<button type="button" class="btn btn-secondary" data-action="detect-mgmt">Rechercher l\'interface Web</button>' : ''}
        ${safeUrl && canDiscover ? '<button type="button" class="btn btn-secondary" data-action="check-mgmt">Tester le lien</button>' : ''}
      </div>
      ${canUpdate ? `
      <div class="asset-actions">
        <label class="sr-only" for="asset-mgmt-url">URL d'administration</label>
        <input id="asset-mgmt-url" type="text" class="form-input" style="flex:1; min-width:200px;" placeholder="https://…" value="${this._escapeAttr(url)}" data-mgmt-url-input>
        <button type="button" class="btn btn-secondary" data-action="save-mgmt">Enregistrer</button>
      </div>` : ''}
    `;

    const applyResponse = (resp) => {
      if (!resp) return;
      asset.management_url = resp.management_url;
      asset.management_url_source = resp.management_url_source;
      asset.management_url_status = resp.management_url_status;
      asset.management_url_detected_at = resp.management_url_detected_at;
      if (resp.details) {
        asset.discovery_data = { ...(asset.discovery_data || {}), web: resp.details };
      }
      this._fillManagementSection(container, asset);
    };
    const run = async (action, successMessage) => {
      try {
        applyResponse(await action());
        this._showToast(successMessage);
      } catch (err) {
        this._showToast(err.message || 'Erreur', 'error');
      }
    };

    container.querySelector('[data-action="detect-mgmt"]')?.addEventListener('click', (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      run(() => detectManagementUrl(asset.id), 'Recherche de l\'interface lancée')
        .finally(() => { button.disabled = false; });
    });
    container.querySelector('[data-action="check-mgmt"]')?.addEventListener('click', (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      run(() => checkManagementUrl(asset.id), 'Lien testé')
        .finally(() => { button.disabled = false; });
    });
    container.querySelector('[data-action="save-mgmt"]')?.addEventListener('click', (event) => {
      const button = event.currentTarget;
      const input = container.querySelector('[data-mgmt-url-input]');
      const value = (input?.value || '').trim();
      button.disabled = true;
      run(() => setManagementUrl(asset.id, value), value ? 'URL enregistrée' : 'URL effacée')
        .finally(() => { button.disabled = false; });
    });
  }

  _showAssetInfoModal(asset) {
    if (!asset) return;
    const value = (field, fallback = '-') => this._escape(asset[field] ?? fallback);
    const room = asset.room?.name || 'Non renseigné';
    const rows = (items) => items.map(([label, field, fallback]) => `
      <div class="asset-info-row"><dt>${label}</dt><dd>${value(field, fallback)}</dd></div>
    `).join('');

    const modal = document.createElement('div');
    modal.className = 'modal-overlay asset-info-modal-overlay';
    modal.innerHTML = `
      <div class="modal-content modal-lg">
          <div class="modal-header">
            <h2>${value('name')}</h2>
            <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body asset-info-modal">
            <div class="admin-tabs asset-modal-tabs" role="tablist" aria-label="Informations de l’équipement">
              <button class="admin-tab admin-tab--active" data-asset-tab="general" aria-selected="true" role="tab">Général</button>
              <button class="admin-tab" data-asset-tab="software" aria-selected="false" role="tab">Système logiciel</button>
              <button class="admin-tab" data-asset-tab="user" aria-selected="false" role="tab">Utilisateur</button>
              <button class="admin-tab" data-asset-tab="management" aria-selected="false" role="tab">Interface</button>
              <button class="admin-tab" data-asset-tab="monitoring" aria-selected="false" role="tab">Supervision</button>
              <button class="admin-tab" data-asset-tab="alerts" aria-selected="false" role="tab">Alertes</button>
              <button class="admin-tab" data-asset-tab="history" aria-selected="false" role="tab">Historique</button>
            </div>
            <div class="asset-modal-panel active" data-asset-panel="general"><section><h3>Identité</h3><dl class="asset-info">
              ${rows([['Référence', 'reference'], ['Type', 'asset_type']])}
              <div class="asset-info-row"><dt>Local</dt><dd>${this._escape(room)}</dd></div>
              <div class="asset-info-row"><dt>Statut</dt><dd>${this._renderStatus(asset.status)}</dd></div>
              ${rows([['Description', 'description']])}
            </dl></section><section><h3>Réseau</h3><dl class="asset-info">
              ${rows([['Adresse IP', 'ip_address'], ['Adresse MAC', 'mac_address'], ['Nom AD', 'computer_name_ad'], ['Domaine', 'domain'], ['Unité organisationnelle', 'organizational_unit']])}
            </dl></section><section><h3>Matériel</h3><dl class="asset-info">
              ${rows([['Fabricant', 'manufacturer'], ['Modèle', 'model'], ['Numéro de série', 'serial_number'], ['Fabricant système', 'manufacturer_system'], ['Processeur', 'cpu_name'], ['Cœurs', 'cpu_cores'], ['RAM totale (Mo)', 'ram_total_mb'], ['RAM libre (Mo)', 'ram_free_mb'], ['Disque total (Mo)', 'disk_total_mb'], ['Disque libre (Mo)', 'disk_free_mb'], ['BIOS', 'bios_version']])}
            </dl></section><section><h3>Notes</h3><p>${value('notes')}</p></section></div>
            <div class="asset-modal-panel" data-asset-panel="software"><section><h3>Système logiciel</h3><dl class="asset-info">
              ${rows([['Système', 'os'], ['Version OS', 'os_version'], ['Build OS', 'os_build'], ['Architecture', 'os_architecture'], ['Version agent', 'agent_version'], ['Source découverte', 'discovery_source'], ['Dernière collecte', 'last_collection'], ['Dernier contrôle', 'last_check'], ['Dernière présence', 'last_seen']])}
            </dl></section></div>
            <div class="asset-modal-panel" data-asset-panel="user"><section><h3>Utilisateur</h3><p class="asset-tab-placeholder">Aucun utilisateur n’est actuellement associé à cet équipement.</p></section></div>
            <div class="asset-modal-panel" data-asset-panel="management"><section><h3>Interface d'administration</h3><div data-asset-management>Chargement...</div></section></div>
            <div class="asset-modal-panel" data-asset-panel="monitoring"><section><h3>Supervision</h3><div data-asset-monitoring>Chargement des contrôles...</div></section></div>
            <div class="asset-modal-panel" data-asset-panel="alerts"><section><h3>Alertes</h3><div data-asset-alerts>Chargement des alertes...</div></section></div>
            <div class="asset-modal-panel" data-asset-panel="history"><section><h3>Historique</h3><div data-asset-history>Chargement de l’historique...</div></section></div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Fermer</button>
            ${authStore.hasPermission('it_asset.update') ? `<button class="btn btn-primary" data-action="edit">Modifier</button>` : ''}
          </div>
      </div>
    `;
    document.body.appendChild(modal);
    const close = () => modal.remove();
    modal.querySelectorAll('[data-action="close"]').forEach(button => button.addEventListener('click', close));
    modal.addEventListener('click', (event) => { if (event.target === modal) close(); });
    modal.querySelectorAll('[data-asset-tab]').forEach(tab => tab.addEventListener('click', () => {
      const target = tab.dataset.assetTab;
      modal.querySelectorAll('[data-asset-tab]').forEach(item => {
        const active = item === tab;
        item.classList.toggle('admin-tab--active', active);
        item.setAttribute('aria-selected', String(active));
      });
      modal.querySelectorAll('[data-asset-panel]').forEach(panel => panel.classList.toggle('active', panel.dataset.assetPanel === target));
    }));
    this._fillManagementSection(modal.querySelector('[data-asset-management]'), asset);
    Promise.all([
      getAssetAlerts(asset.id, null),
      getAssetObservations(asset.id, 20),
      getAssetHistory(asset.id, 50),
    ]).then(([alerts, observations, history]) => {
      const alertItems = Array.isArray(alerts) ? alerts : (alerts.items || []);
      const observationItems = observations.items || observations || [];
      const historyItems = history.items || history || [];
      const formatDate = (value) => value ? new Date(value).toLocaleString('fr-FR') : '-';
      const alertTarget = modal.querySelector('[data-asset-alerts]');
      const monitoringTarget = modal.querySelector('[data-asset-monitoring]');
      const historyTarget = modal.querySelector('[data-asset-history]');
      if (alertTarget) alertTarget.innerHTML = alertItems.length ? alertItems.map(item => `<p><strong>${this._escape(item.severity || '-')}</strong> — ${this._escape(item.message || '-')} <small>${formatDate(item.created_at)}</small></p>`).join('') : '<p>Aucune alerte.</p>';
      if (monitoringTarget) monitoringTarget.innerHTML = observationItems.length ? observationItems.map(item => `<p><strong>${this._escape(item.status || '-')}</strong> — ${this._escape(item.check_method || '-')} — ${item.response_time_ms ?? '-'} ms <small>${formatDate(item.checked_at)}</small></p>`).join('') : '<p>Aucun contrôle enregistré.</p>';
      if (historyTarget) historyTarget.innerHTML = historyItems.length ? historyItems.map(item => `<p><strong>${this._escape(item.field_name || '-')}</strong> : ${this._escape(item.old_value || '-')} → ${this._escape(item.new_value || '-')} <small>${formatDate(item.created_at)}</small></p>`).join('') : '<p>Aucun historique.</p>';
    }).catch(() => {
      ['[data-asset-alerts]', '[data-asset-monitoring]', '[data-asset-history]'].forEach(selector => {
        const target = modal.querySelector(selector);
        if (target) target.textContent = 'Informations indisponibles.';
      });
    });
    modal.querySelector('[data-action="edit"]')?.addEventListener('click', () => {
      close();
      this._showAssetModal(asset);
    });
  }

  _bindEvents() {
    if (!this.element) return;

    this.element.querySelectorAll('[data-section]').forEach(btn => {
      btn.addEventListener('click', () => {
        const section = btn.dataset.section;
        const route = SECTION_ROUTES[section];
        if (route && this.router) {
          this.router.navigate(route);
        } else {
          this.currentSection = section;
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
    const rangeSearch = this.element.querySelector('[data-range-search]');
    if (rangeSearch) {
      rangeSearch.addEventListener('input', () => {
        this.rangeSearch = rangeSearch.value;
        this._renderRangeTable();
      });
    }
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

    this.element.querySelectorAll('[data-action="create-asset"]').forEach(btn => {
      btn.addEventListener('click', () => this._showAssetModal());
    });

    this.element.querySelectorAll('[data-action="create-range"]').forEach(btn => {
      btn.addEventListener('click', () => this._showRangeModal());
    });

    this.element.querySelectorAll('[data-action="edit-asset"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const asset = this.assets.find(a => a.id === parseInt(btn.dataset.assetId));
        if (asset) this._showAssetModal(asset);
      });
    });

    this.element.querySelectorAll('[data-action="scan-range"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (this.selectedRangeId) {
          await this._startScan(this.selectedRangeId);
        }
      });
    });

    this.element.querySelectorAll('[data-action="discover-all"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        await this._startScan(null);
      });
    });

    this.element.querySelectorAll('[data-action="monitor-all"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        this.loading = true;
        this.monitoringSummary = 'Actualisation des équipements en cours…';
        this.render();
        try {
          const result = await monitorAllAssets();
          this.monitoringSummary = `${result.checked || 0} équipement(s) contrôlé(s) : ${result.online || 0} en ligne, ${result.offline || 0} hors ligne.`;
          await this.loadAssets();
        } catch (error) {
          this.monitoringSummary = `Échec de l’actualisation : ${error.message || 'erreur inconnue'}`;
        } finally {
          this.loading = false;
          this.render();
        }
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
        this.alerts = Array.isArray(alerts) ? alerts : (alerts.items || []);
        this.render();
      });
    });

    this.element.querySelectorAll('[data-action="acknowledge-alert"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const alertId = parseInt(btn.dataset.alertId);
        await acknowledgeAlert(this.selectedAssetId, alertId);
        const alerts = await getAssetAlerts(this.selectedAssetId, null);
        this.alerts = Array.isArray(alerts) ? alerts : (alerts.items || []);
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
        } else if (direction === 'next' && this.page < Math.ceil(this.total / this.pageSize)) {
          this.page++;
          this.loadAssets();
        }
      });
    });
  }

  _showAssetModal(asset = null) {
    const isEdit = !!asset;
    const value = (field, fallback = '') => this._escape(asset?.[field] ?? fallback);
    const typeOptions = ASSET_TYPES.map(t =>
      `<option value="${t.value}" ${asset?.asset_type === t.value ? 'selected' : ''}>${t.label}</option>`
    ).join('');
    const statusOptions = ASSET_STATUSES.map(s =>
      `<option value="${s.value}" ${(asset?.status || 'unknown') === s.value ? 'selected' : ''}>${s.label}</option>`
    ).join('');
    const roomOptions = this.rooms.map(r =>
      `<option value="${r.id}" ${asset?.room_id === r.id ? 'selected' : ''}>${this._escape(r.reference)} — ${this._escape(r.name)}</option>`
    ).join('');
    const num = (field) => {
      const v = asset?.[field];
      return v !== null && v !== undefined ? v : '';
    };

    const modal = document.createElement('div');
    modal.className = 'modal-overlay it-asset-form-modal-overlay';
    modal.innerHTML = `
      <div class="modal modal-lg">
        <div class="modal-content it-asset-form-modal">
          <div class="modal-header">
            <h2>${isEdit ? `Modifier l'équipement ${this._escape(asset.reference)}` : 'Nouvel équipement'}</h2>
            <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <fieldset>
                <legend>Identité</legend>
                <div class="form-row">
                  <label><span>Nom *</span><input type="text" name="name" value="${value('name')}" required maxlength="200"></label>
                  <label><span>Type *</span><select name="asset_type" required>
                    <option value="">-- Sélectionner --</option>
                    ${typeOptions}
                  </select></label>
                </div>
                <div class="form-row">
                  <label><span>Salle *</span><select name="room_id" required>
                    <option value="">-- Sélectionner --</option>
                    ${roomOptions}
                  </select></label>
                  <label><span>Statut</span><select name="status">${statusOptions}</select></label>
                </div>
                <div class="form-row">
                  <label><span>Description</span><textarea name="description" rows="2">${value('description')}</textarea></label>
                </div>
              </fieldset>
              <fieldset>
                <legend>Réseau</legend>
                <div class="form-row">
                  <label><span>Adresse IP</span><input type="text" name="ip_address" value="${value('ip_address')}" placeholder="192.168.1.10" maxlength="45"></label>
                  <label><span>Adresse MAC</span><input type="text" name="mac_address" value="${value('mac_address')}" placeholder="aa:bb:cc:dd:ee:ff" maxlength="17"></label>
                </div>
                <div class="form-row">
                  <label class="ad-check"><input type="checkbox" name="wol_enabled" ${asset?.wol_enabled ? 'checked' : ''}><span>Wake-on-LAN</span></label>
                  <label><span>MAC WOL</span><input type="text" name="wol_mac" value="${value('wol_mac')}" maxlength="17"></label>
                </div>
              </fieldset>
              <fieldset>
                <legend>Matériel</legend>
                <div class="form-row">
                  <label><span>Fabricant</span><input type="text" name="manufacturer" value="${value('manufacturer')}" maxlength="200"></label>
                  <label><span>Modèle</span><input type="text" name="model" value="${value('model')}" maxlength="200"></label>
                </div>
                <div class="form-row">
                  <label><span>Numéro de série</span><input type="text" name="serial_number" value="${value('serial_number')}" maxlength="200"></label>
                  <label><span>Fabricant système</span><input type="text" name="manufacturer_system" value="${value('manufacturer_system')}" placeholder="Dell, HP, Lenovo..." maxlength="200"></label>
                </div>
                <div class="form-row">
                  <label><span>Processeur</span><input type="text" name="cpu_name" value="${value('cpu_name')}" maxlength="200"></label>
                  <label><span>Cœurs</span><input type="number" name="cpu_cores" value="${num('cpu_cores')}" min="1" max="256"></label>
                </div>
                <div class="form-row">
                  <label><span>RAM totale (Mo)</span><input type="number" name="ram_total_mb" value="${num('ram_total_mb')}" min="0"></label>
                  <label><span>RAM libre (Mo)</span><input type="number" name="ram_free_mb" value="${num('ram_free_mb')}" min="0"></label>
                </div>
                <div class="form-row">
                  <label><span>Disque total (Mo)</span><input type="number" name="disk_total_mb" value="${num('disk_total_mb')}" min="0"></label>
                  <label><span>Disque libre (Mo)</span><input type="number" name="disk_free_mb" value="${num('disk_free_mb')}" min="0"></label>
                </div>
                <div class="form-row">
                  <label><span>BIOS</span><input type="text" name="bios_version" value="${value('bios_version')}" maxlength="100"></label>
                </div>
              </fieldset>
              <fieldset>
                <legend>Système</legend>
                <div class="form-row">
                  <label><span>OS</span><input type="text" name="os" value="${value('os')}" placeholder="Windows 11, Ubuntu..." maxlength="100"></label>
                  <label><span>Version OS</span><input type="text" name="os_version" value="${value('os_version')}" maxlength="100"></label>
                </div>
                <div class="form-row">
                  <label><span>Build OS</span><input type="text" name="os_build" value="${value('os_build')}" maxlength="50"></label>
                  <label><span>Architecture</span><input type="text" name="os_architecture" value="${value('os_architecture')}" placeholder="64-bit" maxlength="20"></label>
                </div>
              </fieldset>
              <fieldset>
                <legend>Domaine</legend>
                <div class="form-row">
                  <label><span>Domaine Active Directory</span><input type="text" name="domain" value="${value('domain')}" placeholder="mondomaine.local" maxlength="200"></label>
                </div>
              </fieldset>
              <fieldset>
                <legend>Divers</legend>
                <div class="form-row">
                  <label><span>Notes</span><textarea name="notes" rows="2">${value('notes')}</textarea></label>
                </div>
                ${isEdit ? `
                <div class="form-row">
                  <label class="ad-check"><input type="checkbox" name="is_active" ${asset?.is_active !== false ? 'checked' : ''}><span>Équipement actif</span></label>
                </div>` : ''}
              </fieldset>
            </form>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Annuler</button>
            <button class="btn btn-primary" data-action="save">${isEdit ? 'Enregistrer' : 'Créer'}</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const form = modal.querySelector('[data-form]');
      const fd = new FormData(form);
      const data = {};
      const intFields = ['room_id', 'cpu_cores', 'ram_total_mb', 'ram_free_mb', 'disk_total_mb', 'disk_free_mb'];
      for (const [k, v] of fd.entries()) {
        if (v === '') continue;
        data[k] = intFields.includes(k) ? parseInt(v, 10) : v;
      }
      data.wol_enabled = fd.get('wol_enabled') === 'on';
      if (isEdit) data.is_active = fd.get('is_active') === 'on';
      if (!data.name || !data.asset_type || !data.room_id) {
        alert('Les champs Nom, Type et Salle sont obligatoires');
        return;
      }
      try {
        if (isEdit) {
          await updateItAsset(asset.id, data);
        } else {
          await createItAsset(data);
        }
        modal.remove();
        this._showToast(isEdit ? 'Asset mis à jour' : 'Asset créé');
        await this.loadAssets();
      } catch (e) {
        alert(e.message || 'Erreur lors de l\'enregistrement');
      }
    });
  }

  _showRangeModal(range = null) {
    const isEdit = !!range;
    const value = (field, fallback = '') => this._escape(range?.[field] ?? fallback);
    const num = (field, fallback = '') => {
      const v = range?.[field];
      return v !== null && v !== undefined ? v : fallback;
    };

    const roomOptions = [
      '<option value="">Aucun local associé</option>',
      ...this.rooms.map(r => `<option value="${r.id}" ${range?.room_id === r.id ? 'selected' : ''}>${this._escape(r.reference)} — ${this._escape(r.name)}</option>`)
    ].join('');

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <div class="modal-content">
          <div class="modal-header">
            <h2>${isEdit ? `Modifier la plage ${this._escape(range.name)}` : 'Nouvelle plage réseau'}</h2>
            <button class="modal-close" data-action="close" aria-label="Fermer">&times;</button>
          </div>
          <div class="modal-body">
            <form data-form>
              <div class="form-row">
                <label><span>Nom *</span><input type="text" name="name" value="${value('name')}" required maxlength="100"></label>
                <label><span>CIDR *</span><input type="text" name="cidr" value="${value('cidr')}" placeholder="192.168.1.0/24" required maxlength="50"></label>
              </div>
              <div class="form-row">
                <label><span>Local (salle)</span><select name="room_id">${roomOptions}</select></label>
                <label><span>VLAN</span><input type="number" name="vlan_id" value="${num('vlan_id')}" min="0" max="4094"></label>
              </div>
              <div class="form-row">
                <label><span>Intervalle de scan (min)</span><input type="number" name="scan_interval_minutes" value="${num('scan_interval_minutes', 60)}" min="1" max="10080"></label>
              </div>
              <div class="form-row">
                <label><span>Description</span><textarea name="description" rows="2">${value('description')}</textarea></label>
              </div>
              <div class="form-row">
                <label class="ad-check"><input type="checkbox" name="scan_enabled" ${range ? (range.scan_enabled ? 'checked' : '') : 'checked'}><span>Scan actif</span></label>
                <label class="ad-check"><input type="checkbox" name="is_active" ${range ? (range.is_active !== false ? 'checked' : '') : 'checked'}><span>Plage active</span></label>
              </div>
              <fieldset>
                <legend>SNMP</legend>
                <div class="form-row">
                  <label class="ad-check"><input type="checkbox" name="snmp_enabled" ${range?.snmp_enabled ? 'checked' : ''}><span>Collecte SNMP</span></label>
                  <label><span>Version</span><select name="snmp_version">
                    <option value="v2c" ${(range?.snmp_version || 'v2c') === 'v2c' ? 'selected' : ''}>v2c</option>
                    <option value="v1" ${range?.snmp_version === 'v1' ? 'selected' : ''}>v1</option>
                  </select></label>
                </div>
                <div class="form-row">
                  <label><span>Communauté</span><input type="text" name="snmp_community" value="${value('snmp_community')}" placeholder="public" maxlength="100"></label>
                  <label><span>Port</span><input type="number" name="snmp_port" value="${num('snmp_port', 161)}" min="1" max="65535"></label>
                </div>
              </fieldset>
            </form>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="close">Annuler</button>
            <button class="btn btn-primary" data-action="save">${isEdit ? 'Enregistrer' : 'Créer'}</button>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.querySelector('[data-action="close"]')?.addEventListener('click', () => modal.remove());
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    modal.querySelector('[data-action="save"]')?.addEventListener('click', async () => {
      const form = modal.querySelector('[data-form]');
      const fd = new FormData(form);
      const data = {};
      const intFields = ['vlan_id', 'scan_interval_minutes', 'snmp_port', 'room_id'];
      for (const [k, v] of fd.entries()) {
        if (v === '') {
          if (k === 'room_id' && isEdit) data.room_id = null;
          continue;
        }
        data[k] = intFields.includes(k) ? parseInt(v, 10) : v;
      }
      data.scan_enabled = fd.get('scan_enabled') === 'on';
      data.is_active = fd.get('is_active') === 'on';
      data.snmp_enabled = fd.get('snmp_enabled') === 'on';
      if (!data.name || !data.cidr) {
        alert('Les champs Nom et CIDR sont obligatoires');
        return;
      }
      try {
        if (isEdit) {
          await updateNetworkRange(range.id, data);
        } else {
          await createNetworkRange(data);
        }
        modal.remove();
        this._showToast(isEdit ? 'Plage mise à jour' : 'Plage créée');
        await this.loadNetworkRanges();
        this.render();
      } catch (e) {
        alert(e.message || 'Erreur lors de l\'enregistrement');
      }
    });
  }

  _showToast(message, variant = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${variant}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  _escape(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Échappement pour valeur d'attribut (guillemets compris) — réutilise
  // _escape puis échappe les " comme ailleurs dans le projet.
  _escapeAttr(value) {
    return this._escape(value).replace(/"/g, '&quot;');
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
