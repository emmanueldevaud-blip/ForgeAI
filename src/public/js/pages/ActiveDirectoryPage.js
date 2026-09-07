import { 
  getAdConfigs,
  createAdConfig,
  getAdConfig,
  updateAdConfig,
  deleteAdConfig,
  getAdMappings,
  createAdMapping,
  updateAdMapping,
  deleteAdMapping,
  syncAdConfig,
  getAdSyncLogs,
  testAdConfig
} from '../services/adApi.js';

export class ActiveDirectoryPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.configs = [];
    this.selectedConfigId = null;
    this.syncLogs = [];
    this.mappings = [];
    this.currentAdTab = 'config';
  }

  async initialize() {
    await this.loadConfigs();
  }

  async loadConfigs() {
    try {
      const configs = await getAdConfigs();
      if (configs.length > 0 && !this.selectedConfigId) {
        await this.loadConfigDetails(configs[0].id, { config: configs[0], configs });
      } else {
        this.configs = configs;
      }
    } catch (error) {
      console.error('Failed to load AD configs:', error);
    }
  }

  async loadConfigDetails(configId, { config = null, configs = null } = {}) {
    const [loadedConfig, mappings, syncLogs] = await Promise.all([
      config ? Promise.resolve(config) : getAdConfig(configId),
      getAdMappings(configId),
      getAdSyncLogs(configId)
    ]);
    if (configs) this.configs = configs;
    this.selectedConfigId = configId;
    this.currentConfig = loadedConfig;
    this.mappings = mappings;
    this.syncLogs = syncLogs;
    if (this.element) this.render();
  }

  async refreshConfigsAndDetails(preferredConfigId = this.selectedConfigId) {
    const configs = await getAdConfigs();
    const config = configs.find(item => item.id === preferredConfigId) || configs[0];

    if (!config) {
      this.configs = configs;
      this.selectedConfigId = null;
      this.currentConfig = null;
      this.mappings = [];
      this.syncLogs = [];
      if (this.element) this.render();
      return;
    }

    await this.loadConfigDetails(config.id, { config, configs });
  }

  async refreshMappings() {
    const mappings = await getAdMappings(this.selectedConfigId);
    this.mappings = mappings;
    if (this.element) this.render();
  }

  async refreshSyncState() {
    const [config, syncLogs] = await Promise.all([
      getAdConfig(this.selectedConfigId),
      getAdSyncLogs(this.selectedConfigId)
    ]);
    this.currentConfig = config;
    this.syncLogs = syncLogs;
    if (this.element) this.render();
  }

  async handleConfigSelect(configId) {
    try {
      await this.loadConfigDetails(configId);
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleCreateConfig() {
    const name = prompt('Nom de la configuration :');
    if (!name) return;

    try {
      const config = await createAdConfig({
        name,
        is_default: this.configs.length === 0,
        server: '',
        port: 636,
        use_ssl: true,
        base_dn: '',
        user_dn: '',
        user_search_filter: '(sAMAccountName={username})',
        group_search_base: '',
        bind_user: '',
        bind_password: '',
        connect_timeout: 10,
        receive_timeout: 10,
        page_size: 1000,
        follow_referrals: false,
        is_active: true
      });
      await this.refreshConfigsAndDetails(config.id);
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleUpdateConfig(updates) {
    try {
      const config = await updateAdConfig(this.selectedConfigId, updates);
      await this.refreshConfigsAndDetails(config.id);
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleDeleteConfig() {
    if (!confirm('Supprimer cette configuration ?')) return;
    try {
      await deleteAdConfig(this.selectedConfigId);
      await this.refreshConfigsAndDetails();
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleTestConnection() {
    if (!this.currentConfig) return;
    const form = this.element?.querySelector('[data-form="config"]');
    const formData = form ? new FormData(form) : null;
    const bindPassword = formData?.get('bind_password');
    try {
      const result = await testAdConfig({
        ad_config_id: this.selectedConfigId,
        ad_server: formData.get('server'),
        ad_port: parseInt(formData.get('port'), 10),
        ad_use_ssl: form.querySelector('[name="use_ssl"]').checked,
        ad_base_dn: formData.get('base_dn'),
        ad_bind_user: formData.get('bind_user'),
        ad_bind_password: bindPassword || '',
        ad_connect_timeout: parseInt(formData.get('connect_timeout'), 10),
        ad_receive_timeout: parseInt(formData.get('receive_timeout'), 10),
        ad_follow_referrals: form.querySelector('[name="follow_referrals"]').checked,
      });
      alert(result.success ? '✓ Connexion réussie' : '✗ Échec: ' + result.message + (result.details ? '\n' + result.details : ''));
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleSync() {
    if (!this.selectedConfigId) return;
    try {
      const result = await syncAdConfig(this.selectedConfigId);
      await this.refreshSyncState();
      alert(`Synchronisation terminée: ${result.users_processed} utilisateurs traités, ${result.users_created} créés, ${result.users_updated} mis à jour, ${result.users_deactivated} désactivés`);
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleCreateMapping() {
    if (!this.selectedConfigId) return;
    const adGroupCn = prompt('CN du groupe AD :');
    if (!adGroupCn) return;
    const adGroupDn = prompt('DN du groupe AD (optionnel) :');
    const roleCode = prompt('Code rôle ForgeAI (admin/user) :');
    if (!roleCode) return;

    try {
      await createAdMapping(this.selectedConfigId, {
        ad_group_cn: adGroupCn,
        ad_group_dn: adGroupDn || null,
        role_code: roleCode,
        is_active: true,
      });
      await this.refreshMappings();
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleUpdateMapping(mapping) {
    const adGroupCn = prompt('CN du groupe AD :', mapping.ad_group_cn);
    if (!adGroupCn) return;
    const adGroupDn = prompt('DN du groupe AD (optionnel) :', mapping.ad_group_dn || '');
    if (adGroupDn === null) return;
    const roleCode = prompt('Code rôle ForgeAI (admin/user) :', mapping.role_code);
    if (!roleCode) return;
    const activeValue = prompt('Mapping actif (oui/non) :', mapping.is_active ? 'oui' : 'non');
    if (activeValue === null) return;
    const normalizedActiveValue = activeValue.trim().toLowerCase();
    if (normalizedActiveValue !== 'oui' && normalizedActiveValue !== 'non') {
      alert('Répondez « oui » ou « non » pour l’état du mapping.');
      return;
    }

    try {
      await updateAdMapping(this.selectedConfigId, mapping.id, {
        ad_group_cn: adGroupCn,
        ad_group_dn: adGroupDn || null,
        role_code: roleCode,
        is_active: normalizedActiveValue === 'oui',
      });
      await this.refreshMappings();
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  async handleDeleteMapping(mappingId) {
    if (!confirm('Supprimer ce mapping ?')) return;
    try {
      await deleteAdMapping(this.selectedConfigId, mappingId);
      await this.refreshMappings();
    } catch (error) {
      alert('Erreur: ' + error.message);
    }
  }

  render() {
    const previousElement = this.element;
    this.element = document.createElement('div');
    this.element.className = 'ad-page';

    if (!this.currentConfig) {
      this.element.innerHTML = `
        <div class="ad-empty">
          <h2>Active Directory</h2>
          <p>Aucune configuration AD. Créez-en une pour commencer.</p>
          <button class="btn btn-primary" data-action="create-config">Créer une configuration</button>
        </div>
      `;
      this.element.querySelector('[data-action="create-config"]').addEventListener('click', () => this.handleCreateConfig());
      if (previousElement?.parentNode) previousElement.replaceWith(this.element);
      return this.element;
    }

    const isDefault = this.currentConfig.is_default;
    const lastSync = this.currentConfig.last_sync_at ? new Date(this.currentConfig.last_sync_at).toLocaleString('fr-FR') : 'Jamais';
    const lastSyncStatus = this.currentConfig.last_sync_status || '—';

    this.element.innerHTML = `
      <div class="ad-header">
        <div class="ad-title-area">
          <h2>Active Directory</h2>
          <p class="ad-description">Gestion de la connexion et synchronisation Active Directory</p>
        </div>
        <div class="ad-actions">
          <button class="btn btn-secondary" data-action="create-config">Nouvelle config</button>
          <button class="btn btn-danger" data-action="delete-config">Supprimer</button>
        </div>
      </div>

      <div class="ad-content">
        <div class="ad-sidebar">
          <div class="ad-config-list">
            <h3>Configurations</h3>
            <ul>
              ${this.configs.map(cfg => `
                <li class="${cfg.id === this.selectedConfigId ? 'active' : ''}" data-config-id="${cfg.id}">
                  <span class="config-name">${cfg.name}</span>
                  ${cfg.is_default ? '<span class="badge badge-default">Défaut</span>' : ''}
                  ${cfg.is_active ? '<span class="badge badge-active">Actif</span>' : '<span class="badge badge-inactive">Inactif</span>'}
                </li>
              `).join('')}
            </ul>
          </div>
        </div>

        <div class="ad-main">
          <div class="ad-tabs">
            <button class="ad-tab ${this.currentAdTab === 'config' ? 'active' : ''}" data-ad-tab="config">Configuration</button>
            <button class="ad-tab ${this.currentAdTab === 'mappings' ? 'active' : ''}" data-ad-tab="mappings">Mappings Groupes → Rôles</button>
            <button class="ad-tab ${this.currentAdTab === 'sync' ? 'active' : ''}" data-ad-tab="sync">Synchronisation</button>
            <button class="ad-tab ${this.currentAdTab === 'logs' ? 'active' : ''}" data-ad-tab="logs">Historique</button>
          </div>

          <div class="ad-tab-panels">
            <div class="ad-tab-panel ${this.currentAdTab === 'config' ? 'active' : ''}" data-ad-panel="config">
              <form class="ad-form" data-form="config">
                <div class="form-row">
                  <label>
                    <span>Nom</span>
                    <input type="text" name="name" value="${this.currentConfig.name}" required>
                  </label>
                  <label>
                    <span>Configuration par défaut</span>
                    <input type="checkbox" name="is_default" ${isDefault ? 'checked' : ''}>
                  </label>
                </div>

                <fieldset>
                  <legend>Connexion LDAP</legend>
                  <div class="form-row">
                    <label>
                      <span>Serveur</span>
                      <input type="text" name="server" value="${this.currentConfig.server}" required placeholder="ad.example.com">
                    </label>
                    <label>
                      <span>Port</span>
                      <input type="number" name="port" value="${this.currentConfig.port}" min="1" max="65535">
                    </label>
                    <label>
                      <span>LDAPS (SSL/TLS)</span>
                      <input type="checkbox" name="use_ssl" ${this.currentConfig.use_ssl ? 'checked' : ''}>
                    </label>
                  </div>
                  <div class="form-row">
                    <label>
                      <span>Base DN</span>
                      <input type="text" name="base_dn" value="${this.currentConfig.base_dn}" required placeholder="DC=example,DC=com">
                    </label>
                    <label>
                      <span>User DN (optionnel)</span>
                      <input type="text" name="user_dn" value="${this.currentConfig.user_dn || ''}" placeholder="OU=Users,DC=example,DC=com">
                    </label>
                  </div>
                  <div class="form-row">
                    <label>
                      <span>Filtre recherche utilisateur</span>
                      <input type="text" name="user_search_filter" value="${this.currentConfig.user_search_filter}" placeholder="(sAMAccountName={username})">
                    </label>
                  </div>
                  <div class="form-row">
                    <label>
                      <span>Base recherche groupes</span>
                      <input type="text" name="group_search_base" value="${this.currentConfig.group_search_base || ''}" placeholder="OU=Groups,DC=example,DC=com">
                    </label>
                  </div>
                </fieldset>

                <fieldset>
                  <legend>Compte de service (Bind)</legend>
                  <div class="form-row">
                    <label>
                      <span>Bind User</span>
                      <input type="text" name="bind_user" value="${this.currentConfig.bind_user}" required placeholder="CN=svc_forgeai,OU=ServiceAccounts,DC=example,DC=com">
                    </label>
                    <label>
                      <span>Bind Password</span>
                      <input type="password" name="bind_password" placeholder="Laisser vide pour ne pas changer" autocomplete="new-password">
                    </label>
                  </div>
                </fieldset>

                <fieldset>
                  <legend>Timeouts</legend>
                  <div class="form-row">
                    <label>
                      <span>Connexion (s)</span>
                      <input type="number" name="connect_timeout" value="${this.currentConfig.connect_timeout}" min="1" max="60">
                    </label>
                    <label>
                      <span>Réception (s)</span>
                      <input type="number" name="receive_timeout" value="${this.currentConfig.receive_timeout}" min="1" max="60">
                    </label>
                    <label>
                      <span>Taille page</span>
                      <input type="number" name="page_size" value="${this.currentConfig.page_size}" min="100" max="5000">
                    </label>
                  </div>
                </fieldset>

                <div class="form-row">
                  <label>
                    <span>Configuration active</span>
                    <input type="checkbox" name="is_active" ${this.currentConfig.is_active ? 'checked' : ''}>
                  </label>
                  <label>
                    <span>Suivre les références</span>
                    <input type="checkbox" name="follow_referrals" ${this.currentConfig.follow_referrals ? 'checked' : ''}>
                  </label>
                </div>

                <div class="form-actions">
                  <button type="submit" class="btn btn-primary">Enregistrer</button>
                  <button type="button" class="btn btn-secondary" data-action="test-connection">Tester la connexion</button>
                </div>
              </form>
            </div>

            <div class="ad-tab-panel ${this.currentAdTab === 'mappings' ? 'active' : ''}" data-ad-panel="mappings">
              <div class="mappings-toolbar">
                <h3>Mapping Groupes AD → Rôles ForgeAI</h3>
                <button class="btn btn-primary" data-action="create-mapping">Ajouter un mapping</button>
              </div>
              <table class="ad-table">
                <thead>
                  <tr>
                    <th>Groupe AD (CN)</th>
                    <th>DN Groupe AD</th>
                    <th>Rôle ForgeAI</th>
                    <th>Actif</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  ${this.mappings.length === 0 ? `
                    <tr><td colspan="5" class="empty">Aucun mapping configuré</td></tr>
                  ` : this.mappings.map(m => `
                    <tr data-mapping-id="${m.id}">
                      <td>${m.ad_group_cn}</td>
                      <td>${m.ad_group_dn || '—'}</td>
                      <td><span class="role-badge ${m.role_code}">${m.role_code}</span></td>
                      <td>${m.is_active ? '<span class="badge badge-active">Oui</span>' : '<span class="badge badge-inactive">Non</span>'}</td>
                      <td>
                        <button class="btn btn-icon" data-action="update-mapping" data-mapping-id="${m.id}" title="Modifier">✏️</button>
                        <button class="btn btn-icon btn-danger" data-action="delete-mapping" data-mapping-id="${m.id}" title="Supprimer">🗑️</button>
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>

            <div class="ad-tab-panel ${this.currentAdTab === 'sync' ? 'active' : ''}" data-ad-panel="sync">
              <div class="sync-status">
                <h3>État de la synchronisation</h3>
                <div class="sync-info">
                  <div class="sync-item">
                    <span class="sync-label">Dernière synchronisation</span>
                    <span class="sync-value">${lastSync}</span>
                  </div>
                  <div class="sync-item">
                    <span class="sync-label">Statut</span>
                    <span class="sync-value status-${lastSyncStatus}">${lastSyncStatus}</span>
                  </div>
                </div>
              </div>
              <div class="sync-actions">
                <button class="btn btn-primary btn-lg" data-action="sync" ${!this.currentConfig.is_active ? 'disabled' : ''}>
                  Lancer la synchronisation
                </button>
                ${!this.currentConfig.is_active ? '<p class="text-muted">Activez la configuration pour synchroniser</p>' : ''}
              </div>

              ${this.syncLogs.length > 0 ? `
                <div class="sync-recent">
                  <h3>Dernières synchronisations</h3>
                  <table class="ad-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Statut</th>
                        <th>Utilisateurs traités</th>
                        <th>Créés</th>
                        <th>Mis à jour</th>
                        <th>Désactivés</th>
                        <th>Groupes</th>
                        <th>Erreur</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${this.syncLogs.slice(0, 10).map(log => `
                        <tr>
                          <td>${new Date(log.started_at).toLocaleString('fr-FR')}</td>
                          <td><span class="badge badge-${log.status}">${log.status}</span></td>
                          <td>${log.users_processed}</td>
                          <td>${log.users_created}</td>
                          <td>${log.users_updated}</td>
                          <td>${log.users_deactivated}</td>
                          <td>${log.groups_processed || 0}</td>
                          <td>${log.error_message || '—'}</td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                </div>
              ` : ''}
            </div>

            <div class="ad-tab-panel ${this.currentAdTab === 'logs' ? 'active' : ''}" data-ad-panel="logs">
              <h3>Historique complet des synchronisations</h3>
              ${this.syncLogs.length === 0 ? `
                <p class="text-muted">Aucun historique</p>
              ` : `
                <table class="ad-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Statut</th>
                      <th>Utilisateurs traités</th>
                      <th>Créés</th>
                      <th>Mis à jour</th>
                      <th>Désactivés</th>
                      <th>Groupes</th>
                      <th>Erreur</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${this.syncLogs.map(log => `
                      <tr>
                        <td>${new Date(log.started_at).toLocaleString('fr-FR')}</td>
                        <td><span class="badge badge-${log.status}">${log.status}</span></td>
                        <td>${log.users_processed}</td>
                        <td>${log.users_created}</td>
                        <td>${log.users_updated}</td>
                        <td>${log.users_deactivated}</td>
                        <td>${log.groups_processed || 0}</td>
                        <td>${log.error_message || '—'}</td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              `}
            </div>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    if (previousElement?.parentNode) previousElement.replaceWith(this.element);
    return this.element;
  }

  bindEvents() {
    this.element.querySelectorAll('[data-config-id]').forEach(li => {
      li.addEventListener('click', () => this.handleConfigSelect(parseInt(li.dataset.configId)));
    });

    this.element.querySelector('[data-action="create-config"]')?.addEventListener('click', () => this.handleCreateConfig());
    this.element.querySelector('[data-action="delete-config"]')?.addEventListener('click', () => this.handleDeleteConfig());
    this.element.querySelector('[data-action="test-connection"]')?.addEventListener('click', () => this.handleTestConnection());
    this.element.querySelector('[data-action="sync"]')?.addEventListener('click', () => this.handleSync());
    this.element.querySelector('[data-action="create-mapping"]')?.addEventListener('click', () => this.handleCreateMapping());

    this.element.querySelectorAll('[data-action="update-mapping"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const mapping = this.mappings.find(item => item.id === parseInt(btn.dataset.mappingId));
        if (mapping) this.handleUpdateMapping(mapping);
      });
    });

    this.element.querySelectorAll('[data-action="delete-mapping"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.handleDeleteMapping(parseInt(btn.dataset.mappingId));
      });
    });

    this.element.querySelectorAll('[data-ad-tab]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.currentAdTab = btn.dataset.adTab;
        this.render();
      });
    });

    const form = this.element.querySelector('[data-form="config"]');
    form?.addEventListener('submit', (e) => {
      e.preventDefault();
      const formData = new FormData(form);
      const updates = {};
      for (const [key, value] of formData.entries()) {
        if (key === 'is_default' || key === 'use_ssl' || key === 'is_active' || key === 'follow_referrals') {
          updates[key] = form.querySelector(`[name="${key}"]`).checked;
        } else if (key === 'port' || key === 'connect_timeout' || key === 'receive_timeout' || key === 'page_size') {
          updates[key] = parseInt(value, 10);
        } else if (key === 'bind_password' && value === '') {
          continue;
        } else {
          updates[key] = value;
        }
      }
      this.handleUpdateConfig(updates);
    });
  }

  destroy() {
    this.element = null;
  }
}

export function createActiveDirectoryPage(router) {
  return new ActiveDirectoryPage(router);
}
