import {
  createAdConfig,
  createAdMapping,
  deleteAdConfig,
  deleteAdMapping,
  getAdConfig,
  getAdConfigs,
  getAdMappings,
  getAdSyncLogs,
  syncAdConfig,
  testAdConfig,
  updateAdConfig,
  updateAdMapping,
} from '../services/adApi.js';
import { ConfirmDialog } from '../components/ConfirmDialog.js';

const DEFAULT_CONFIG = {
  name: '', is_default: false, server: '', port: 636, use_ssl: true,
  base_dn: '', user_dn: '', user_search_filter: '(sAMAccountName={username})',
  group_search_filter: '(&(objectCategory=group)(cn=GG_FORGEAI*))',
  group_search_base: '', bind_user: '', bind_password: '', connect_timeout: 10,
  receive_timeout: 10, page_size: 1000, follow_referrals: false, is_active: true,
};

const BOOLEAN_FIELDS = ['is_default', 'use_ssl', 'is_active', 'follow_referrals'];
const NUMBER_FIELDS = ['port', 'connect_timeout', 'receive_timeout', 'page_size'];

export class ActiveDirectoryPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.configs = [];
    this.loading = false;
    this.loadError = null;
    this.modal = null;
    this.modalKeydown = null;
    this.lastFocusedElement = null;
    this.notice = null;
  }

  async initialize() {
    await this.refreshConfigs();
  }

  async refreshConfigs() {
    this.loading = true;
    this.loadError = null;
    this.render();
    try {
      this.configs = await getAdConfigs();
      this.loadError = null;
    } catch (error) {
      this.loadError = `Impossible de charger les configurations AD : ${this.safeMessage(error.message)}`;
    } finally {
      this.loading = false;
      this.render();
    }
  }

  escape(value = '') {
    const node = document.createElement('div');
    node.textContent = value ?? '';
    return node.innerHTML;
  }

  formatDate(value) {
    if (!value) return 'Jamais';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('fr-FR');
  }

  safeMessage(value = '') {
    return String(value)
      .replace(/(bind_password|password|mot de passe)(\s*[:=]\s*)[^\s,;]+/gi, '$1$2[masqué]');
  }

  setNotice(type, message) {
    this.notice = { type, message };
    this.render();
  }

  render() {
    const previousElement = this.element;
    this.element = document.createElement('section');
    this.element.className = 'ad-page ad-management-page';
    const notice = this.notice ? `<div class="ad-management-notice ${this.notice.type}" role="status">${this.escape(this.notice.message)}</div>` : '';
    const content = this.loading
      ? '<div class="ad-empty-state ad-load-state" role="status">Chargement des configurations Active Directory…</div>'
      : this.loadError
        ? `<div class="ad-empty-state ad-load-state ad-load-error" role="alert">${this.escape(this.loadError)}</div>`
        : this.configs.length
          ? this.configs.map(config => this.renderConfigCard(config)).join('')
          : `<div class="ad-empty-state"><h3>Aucune configuration Active Directory</h3><p>Créez une configuration avec le bouton ci-dessus pour connecter ForgeAI à votre annuaire.</p></div>`;

    this.element.innerHTML = `
      <header class="ad-management-header">
        <div>
          <h2>Configuration Active Directory</h2>
          <p>Gérez les connexions, mappings, synchronisations et historiques Active Directory.</p>
        </div>
        <button type="button" class="btn btn-primary" data-action="create-config">+ Ajouter une configuration</button>
      </header>
      ${notice}
      <div class="ad-config-cards">${content}</div>
    `;

    this.bindPageEvents();
    if (previousElement?.parentNode) previousElement.replaceWith(this.element);
    return this.element;
  }

  renderConfigCard(config) {
    const status = config.is_active ? 'Actif' : 'Inactif';
    return `
      <article class="ad-config-card" data-config-id="${config.id}">
        <div class="ad-config-card__heading">
          <div>
            <h3>${this.escape(config.name)}</h3>
            ${config.is_default ? '<span class="badge badge-default">Par défaut</span>' : ''}
          </div>
          <span class="badge ${config.is_active ? 'badge-active' : 'badge-inactive'}">${status}</span>
        </div>
        <dl class="ad-config-summary">
          <div><dt>Serveur</dt><dd>${this.escape(config.server)}</dd></div>
          <div><dt>Port</dt><dd>${this.escape(String(config.port))}</dd></div>
          <div><dt>SSL / LDAPS</dt><dd>${config.use_ssl ? 'Activé' : 'Désactivé'}</dd></div>
          <div><dt>Compte Bind</dt><dd>${this.escape(config.bind_user)}</dd></div>
          <div><dt>Dernière synchronisation</dt><dd>${this.escape(this.formatDate(config.last_sync_at))}</dd></div>
        </dl>
        <div class="ad-config-card__actions">
          <button type="button" class="btn btn-secondary" data-action="edit-config" data-config-id="${config.id}">Modifier</button>
          <button type="button" class="btn btn-secondary" data-action="test-config" data-config-id="${config.id}">Tester</button>
          <button type="button" class="btn btn-secondary" data-action="mappings" data-config-id="${config.id}">Mappings</button>
          <button type="button" class="btn btn-secondary" data-action="logs" data-config-id="${config.id}">Logs</button>
          <button type="button" class="btn btn-primary" data-action="sync" data-config-id="${config.id}" ${config.is_active ? '' : 'disabled'}>Synchroniser</button>
          <button type="button" class="btn btn-secondary" data-action="toggle-config" data-config-id="${config.id}">${config.is_active ? 'Désactiver' : 'Activer'}</button>
          <button type="button" class="btn btn-danger" data-action="delete-config" data-config-id="${config.id}">Supprimer</button>
        </div>
      </article>
    `;
  }

  bindPageEvents() {
    this.element.querySelectorAll('[data-action="create-config"]').forEach(button => button.addEventListener('click', () => this.openConfigModal()));
    this.element.querySelectorAll('[data-config-id]').forEach(button => {
      const id = Number(button.dataset.configId);
      const action = button.dataset.action;
      if (action === 'edit-config') button.addEventListener('click', () => this.openConfigModal(id));
      if (action === 'test-config') button.addEventListener('click', () => this.openTestModal(id));
      if (action === 'mappings') button.addEventListener('click', () => this.openMappingsModal(id));
      if (action === 'logs') button.addEventListener('click', () => this.openLogsModal(id));
      if (action === 'sync') button.addEventListener('click', () => this.confirmSync(id));
      if (action === 'toggle-config') button.addEventListener('click', () => this.toggleConfig(id));
      if (action === 'delete-config') button.addEventListener('click', () => this.confirmDeleteConfig(id));
    });
  }

  openModal({ title, content, onMount, closeOnOverlay = true, closeOnEscape = true }) {
    this.closeModal();
    this.lastFocusedElement = document.activeElement;
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay ad-modal-overlay';
    const dialog = document.createElement('div');
    dialog.className = 'modal ad-modal';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'ad-modal-title');
    dialog.innerHTML = `
      <div class="modal-content ad-modal-content">
        <div class="modal-header">
          <h2 id="ad-modal-title">${this.escape(title)}</h2>
          <button type="button" class="modal-close" aria-label="Fermer" data-action="close-modal">×</button>
        </div>
        <div class="modal-body ad-modal-body">${content}</div>
      </div>
    `;
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    this.modal = { overlay, dialog, closeOnOverlay, closeOnEscape };
    dialog.querySelector('[data-action="close-modal"]').addEventListener('click', () => this.closeModal());
    overlay.addEventListener('click', event => { if (closeOnOverlay && event.target === overlay) this.closeModal(); });
    this.modalKeydown = event => this.handleModalKeydown(event);
    document.addEventListener('keydown', this.modalKeydown);
    requestAnimationFrame(() => { overlay.classList.add('open'); dialog.classList.add('open'); });
    setTimeout(() => (dialog.querySelector('[autofocus], input, select, button') || dialog).focus(), 0);
    onMount?.(dialog);
    return dialog;
  }

  handleModalKeydown(event) {
    if (!this.modal) return;
    if (event.key === 'Escape' && this.modal.closeOnEscape) { event.preventDefault(); this.closeModal(); return; }
    if (event.key !== 'Tab') return;
    const focusable = [...this.modal.dialog.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  closeModal() {
    if (!this.modal) return;
    const { overlay, dialog } = this.modal;
    document.removeEventListener('keydown', this.modalKeydown);
    overlay.classList.remove('open');
    dialog.classList.remove('open');
    setTimeout(() => overlay.remove(), 200);
    this.modal = null;
    this.modalKeydown = null;
    if (this.lastFocusedElement?.isConnected) this.lastFocusedElement.focus();
    this.lastFocusedElement = null;
  }

  configForm(config, isNew) {
    const value = (key) => this.escape(String(config[key] ?? ''));
    const checked = key => config[key] ? 'checked' : '';
    return `
      <form class="ad-modal-form" data-form="config" novalidate>
        <div class="form-row"><label><span>Nom</span><input name="name" value="${value('name')}" required autofocus></label><label class="ad-check"><input type="checkbox" name="is_default" ${checked('is_default')}><span>Configuration par défaut</span></label></div>
        <fieldset><legend>Connexion LDAP</legend>
          <div class="form-row"><label><span>Serveur</span><input name="server" value="${value('server')}" required placeholder="ad.example.com"></label><label><span>Port</span><input type="number" name="port" value="${value('port')}" min="1" max="65535" required></label><label class="ad-check"><input type="checkbox" name="use_ssl" ${checked('use_ssl')}><span>LDAPS (SSL/TLS)</span></label></div>
          <div class="form-row"><label><span>Base DN</span><input name="base_dn" value="${value('base_dn')}" required placeholder="DC=example,DC=com"></label><label><span>User DN (optionnel)</span><input name="user_dn" value="${value('user_dn')}"></label></div>
          <div class="form-row"><label><span>Filtre recherche utilisateur</span><input name="user_search_filter" value="${value('user_search_filter')}" required></label><label><span>Filtre recherche groupes</span><input name="group_search_filter" value="${value('group_search_filter')}" required></label></div>
          <div class="form-row"><label><span>Base recherche groupes</span><input name="group_search_base" value="${value('group_search_base')}"></label><label></label></div>
        </fieldset>
        <fieldset><legend>Compte de service (Bind)</legend><div class="form-row"><label><span>Utilisateur de connexion</span><input name="bind_user" value="${value('bind_user')}" required></label><label><span>Mot de passe</span><input type="password" name="bind_password" placeholder="${isNew ? 'Mot de passe du compte de service' : 'Laisser vide pour conserver le mot de passe'}" autocomplete="new-password"></label></div></fieldset>
        <fieldset><legend>Paramètres avancés</legend><div class="form-row"><label><span>Connexion (s)</span><input type="number" name="connect_timeout" value="${value('connect_timeout')}" min="1" max="60" required></label><label><span>Réception (s)</span><input type="number" name="receive_timeout" value="${value('receive_timeout')}" min="1" max="60" required></label><label><span>Taille page</span><input type="number" name="page_size" value="${value('page_size')}" min="100" max="5000" required></label></div><div class="form-row"><label class="ad-check"><input type="checkbox" name="is_active" ${checked('is_active')}><span>Configuration active</span></label><label class="ad-check"><input type="checkbox" name="follow_referrals" ${checked('follow_referrals')}><span>Suivre les références</span></label></div></fieldset>
        <p class="ad-modal-feedback" aria-live="polite" data-feedback></p>
        <div class="form-actions"><button type="button" class="btn btn-secondary" data-action="test-form">Tester la connexion</button><button type="button" class="btn btn-secondary" data-action="close-modal">Annuler</button><button type="submit" class="btn btn-primary">Enregistrer</button></div>
      </form>
    `;
  }

  formPayload(form, isNew) {
    const data = new FormData(form);
    const payload = {};
    for (const [key, rawValue] of data.entries()) {
      if (BOOLEAN_FIELDS.includes(key)) payload[key] = form.elements[key].checked;
      else if (NUMBER_FIELDS.includes(key)) payload[key] = Number(rawValue);
      else if (key !== 'bind_password' || rawValue || isNew) payload[key] = rawValue;
    }
    for (const key of BOOLEAN_FIELDS) if (!(key in payload)) payload[key] = false;
    return payload;
  }

  async openConfigModal(configId = null) {
    let config = { ...DEFAULT_CONFIG, is_default: this.configs.length === 0 };
    if (configId) {
      try { config = await getAdConfig(configId); } catch (error) { this.setNotice('error', this.safeMessage(error.message)); return; }
    }
    const isNew = !configId;
    const dialog = this.openModal({ title: isNew ? 'Nouvelle configuration AD' : 'Modifier la configuration AD', content: this.configForm(config, isNew), closeOnOverlay: false, closeOnEscape: false });
    const form = dialog.querySelector('[data-form="config"]');
    dialog.querySelector('.ad-modal-body [data-action="close-modal"]').addEventListener('click', () => this.closeModal());
    dialog.querySelector('[data-action="test-form"]').addEventListener('click', () => this.testFormConnection(form, configId));
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const feedback = form.querySelector('[data-feedback]');
      const submit = form.querySelector('[type="submit"]');
      submit.disabled = true; feedback.textContent = 'Enregistrement…';
      try {
        const payload = this.formPayload(form, isNew);
        const saved = isNew ? await createAdConfig(payload) : await updateAdConfig(configId, payload);
        this.closeModal();
        await this.refreshConfigs();
        this.setNotice('success', `Configuration « ${saved.name} » enregistrée.`);
      } catch (error) { feedback.textContent = this.safeMessage(error.message); feedback.classList.add('error'); }
      finally { submit.disabled = false; }
    });
  }

  testPayload(form, configId = null) {
    const payload = this.formPayload(form, false);
    return {
      ad_config_id: configId || undefined,
      ad_server: payload.server,
      ad_port: payload.port,
      ad_use_ssl: payload.use_ssl,
      ad_base_dn: payload.base_dn,
      ad_bind_user: payload.bind_user,
      ad_bind_password: payload.bind_password || '',
      ad_connect_timeout: payload.connect_timeout,
      ad_receive_timeout: payload.receive_timeout,
      ad_follow_referrals: payload.follow_referrals,
    };
  }

  testResultMarkup(result) {
    return `<div class="ad-test-state ${result.success ? 'success' : 'error'}"><strong>${result.success ? 'Connexion réussie' : 'Connexion échouée'}</strong><p>${this.escape(this.safeMessage(result.message))}</p>${result.details ? `<pre>${this.escape(this.safeMessage(result.details))}</pre>` : ''}</div>`;
  }

  async testFormConnection(form, configId = null) {
    if (!form.reportValidity()) return;
    const feedback = form.querySelector('[data-feedback]');
    const button = form.querySelector('[data-action="test-form"]');
    button.disabled = true;
    feedback.className = 'ad-modal-feedback is-loading';
    feedback.textContent = 'Test de la connexion LDAP en cours…';
    try {
      const result = await testAdConfig(this.testPayload(form, configId));
      feedback.className = 'ad-modal-feedback';
      feedback.innerHTML = this.testResultMarkup(result);
    } catch (error) {
      feedback.className = 'ad-modal-feedback';
      feedback.innerHTML = `<div class="ad-test-state error"><strong>Test indisponible</strong><p>${this.escape(this.safeMessage(error.message))}</p></div>`;
    } finally {
      button.disabled = false;
    }
  }

  async openTestModal(configId) {
    let config;
    try {
      config = await getAdConfig(configId);
    } catch (error) {
      this.setNotice('error', this.safeMessage(error.message));
      return;
    }
    const dialog = this.openModal({ title: 'Tester la connexion', content: '<div class="ad-test-state is-loading" role="status">Test de la connexion LDAP en cours…</div>', closeOnOverlay: false, closeOnEscape: false });
    const form = document.createElement('form');
    form.innerHTML = this.configForm(config, false);
    try {
      const result = await testAdConfig(this.testPayload(form.querySelector('form') || form, configId));
      dialog.querySelector('.ad-modal-body').innerHTML = `${this.testResultMarkup(result)}<div class="form-actions"><button type="button" class="btn btn-primary" data-action="close-modal">Fermer</button></div>`;
    } catch (error) {
      dialog.querySelector('.ad-modal-body').innerHTML = `<div class="ad-test-state error"><strong>Test indisponible</strong><p>${this.escape(this.safeMessage(error.message))}</p></div><div class="form-actions"><button type="button" class="btn btn-primary" data-action="close-modal">Fermer</button></div>`;
    }
    dialog.querySelector('.ad-modal-body [data-action="close-modal"]').addEventListener('click', () => this.closeModal());
  }

  async toggleConfig(id) {
    const config = this.configs.find(item => item.id === id);
    try { await updateAdConfig(id, { is_active: !config.is_active }); await this.refreshConfigs(); this.setNotice('success', `Configuration ${config.is_active ? 'désactivée' : 'activée'}.`); }
    catch (error) { this.setNotice('error', this.safeMessage(error.message)); }
  }

  confirmDeleteConfig(id) {
    const config = this.configs.find(item => item.id === id);
    new ConfirmDialog({ onConfirm: async () => { try { await deleteAdConfig(id); await this.refreshConfigs(); this.setNotice('success', `Configuration « ${config.name} » supprimée.`); } catch (error) { this.setNotice('error', this.safeMessage(error.message)); } } }).open({ title: 'Supprimer la configuration', message: `Supprimer définitivement « ${config.name} » ?`, confirmText: 'Supprimer', variant: 'danger' });
  }

  confirmSync(id) {
    const config = this.configs.find(item => item.id === id);
    new ConfirmDialog({ onConfirm: () => this.runSync(id, config.name) }).open({ title: 'Lancer la synchronisation', message: `Lancer la synchronisation de « ${config.name} » ?`, confirmText: 'Lancer', variant: 'primary' });
  }

  async runSync(id, name) {
    const dialog = this.openModal({ title: 'Synchronisation Active Directory', content: '<div class="ad-test-state is-loading" role="status">Synchronisation en cours…</div>', closeOnOverlay: false, closeOnEscape: false });
    try {
      const result = await syncAdConfig(id);
      await this.refreshConfigs();
      dialog.querySelector('.ad-modal-body').innerHTML = `<div class="ad-sync-result success"><strong>Synchronisation terminée</strong><dl><div><dt>Utilisateurs traités</dt><dd>${result.users_processed || 0}</dd></div><div><dt>Créés</dt><dd>${result.users_created || 0}</dd></div><div><dt>Mis à jour</dt><dd>${result.users_updated || 0}</dd></div><div><dt>Ignorés / désactivés</dt><dd>${result.users_ignored ?? result.users_skipped ?? result.users_deactivated ?? 0}</dd></div><div><dt>Erreurs</dt><dd>${result.errors_count ?? result.users_errors ?? 0}</dd></div><div><dt>Groupes</dt><dd>${result.groups_processed || 0}</dd></div></dl></div><div class="form-actions"><button type="button" class="btn btn-primary" data-action="close-modal">Fermer</button></div>`;
      dialog.querySelector('.ad-modal-body [data-action="close-modal"]').addEventListener('click', () => this.closeModal());
      this.setNotice('success', `Synchronisation de « ${name} » terminée.`);
    } catch (error) {
      dialog.querySelector('.ad-modal-body').innerHTML = `<div class="ad-test-state error"><strong>Synchronisation échouée</strong><p>${this.escape(this.safeMessage(error.message))}</p></div><div class="form-actions"><button type="button" class="btn btn-primary" data-action="close-modal">Fermer</button></div>`;
      dialog.querySelector('.ad-modal-body [data-action="close-modal"]').addEventListener('click', () => this.closeModal());
    }
  }

  async openMappingsModal(id) {
    let mappings;
    try { mappings = await getAdMappings(id); } catch (error) { this.setNotice('error', this.safeMessage(error.message)); return; }
    const config = this.configs.find(item => item.id === id);
    const content = `<div class="ad-modal-toolbar"><p>${this.escape(config.name)}</p><button class="btn btn-primary" data-action="add-mapping">+ Ajouter un mapping</button></div><div class="ad-modal-table-wrap"><table class="ad-table"><thead><tr><th>Groupe AD</th><th>Rôle</th><th>Actif</th><th></th></tr></thead><tbody>${mappings.length ? mappings.map(mapping => `<tr><td>${this.escape(mapping.ad_group_cn)}${mapping.ad_group_dn ? `<small>${this.escape(mapping.ad_group_dn)}</small>` : ''}</td><td>${this.escape(mapping.role_code)}</td><td>${mapping.is_active ? 'Oui' : 'Non'}</td><td><button class="btn btn-secondary" data-action="edit-mapping" data-mapping-id="${mapping.id}">Modifier</button> <button class="btn btn-danger" data-action="delete-mapping" data-mapping-id="${mapping.id}">Supprimer</button></td></tr>`).join('') : '<tr><td colspan="4" class="empty">Aucun mapping configuré</td></tr>'}</tbody></table></div>`;
    const dialog = this.openModal({ title: 'Mappings AD', content });
    dialog.querySelector('[data-action="add-mapping"]')?.addEventListener('click', () => this.openMappingEditor(id));
    dialog.querySelectorAll('[data-action="edit-mapping"]').forEach(button => button.addEventListener('click', () => this.openMappingEditor(id, mappings.find(item => item.id === Number(button.dataset.mappingId)))));
    dialog.querySelectorAll('[data-action="delete-mapping"]').forEach(button => button.addEventListener('click', () => this.confirmDeleteMapping(id, Number(button.dataset.mappingId))));
  }

  openMappingEditor(configId, mapping = null) {
    const isNew = !mapping;
    const content = `<form class="ad-modal-form" data-form="mapping"><label><span>Groupe AD (CN)</span><input name="ad_group_cn" value="${this.escape(mapping?.ad_group_cn || '')}" required autofocus></label><label><span>DN du groupe (optionnel)</span><input name="ad_group_dn" value="${this.escape(mapping?.ad_group_dn || '')}"></label><label><span>Code du rôle ForgeAI</span><input name="role_code" value="${this.escape(mapping?.role_code || 'user')}" required placeholder="bureau_etudes"></label><label class="ad-check"><input type="checkbox" name="is_active" ${mapping?.is_active !== false ? 'checked' : ''}><span>Mapping actif</span></label><p class="ad-modal-feedback" data-feedback></p><div class="form-actions"><button type="button" class="btn btn-secondary" data-action="close-modal">Annuler</button><button type="submit" class="btn btn-primary">Enregistrer</button></div></form>`;
    const dialog = this.openModal({ title: isNew ? 'Nouveau mapping AD' : 'Modifier le mapping AD', content, closeOnOverlay: false, closeOnEscape: false });
    const form = dialog.querySelector('form');
    dialog.querySelector('.ad-modal-body [data-action="close-modal"]').addEventListener('click', () => this.closeModal());
    form.addEventListener('submit', async event => { event.preventDefault(); if (!form.reportValidity()) return; const payload = { ad_group_cn: form.ad_group_cn.value, ad_group_dn: form.ad_group_dn.value || null, role_code: form.role_code.value, is_active: form.is_active.checked }; const submit = form.querySelector('[type="submit"]'); submit.disabled = true; try { if (isNew) await createAdMapping(configId, payload); else await updateAdMapping(configId, mapping.id, payload); this.closeModal(); await this.openMappingsModal(configId); await this.refreshConfigs(); } catch (error) { form.querySelector('[data-feedback]').textContent = this.safeMessage(error.message); } finally { submit.disabled = false; } });
  }

  confirmDeleteMapping(configId, mappingId) {
    new ConfirmDialog({ onConfirm: async () => { try { await deleteAdMapping(configId, mappingId); await this.openMappingsModal(configId); await this.refreshConfigs(); } catch (error) { this.setNotice('error', this.safeMessage(error.message)); } } }).open({ title: 'Supprimer le mapping', message: 'Supprimer ce mapping de groupe AD ?', confirmText: 'Supprimer', variant: 'danger' });
  }

  async openLogsModal(id) {
    try {
      const logs = await getAdSyncLogs(id);
      const content = `<div class="ad-modal-table-wrap"><table class="ad-table"><thead><tr><th>Date</th><th>Statut</th><th>Utilisateurs</th><th>Résumé</th></tr></thead><tbody>${logs.length ? logs.map(log => `<tr><td>${this.escape(this.formatDate(log.started_at))}</td><td>${this.escape(log.status)}</td><td>${log.users_processed || 0}</td><td>Créés : ${log.users_created || 0} · Mis à jour : ${log.users_updated || 0}${log.error_message ? `<details><summary>Erreur</summary><span>${this.escape(this.safeMessage(log.error_message))}</span></details>` : ''}</td></tr>`).join('') : '<tr><td colspan="4" class="empty">Aucun historique de synchronisation</td></tr>'}</tbody></table></div>`;
      this.openModal({ title: 'Logs de synchronisation', content });
    } catch (error) { this.setNotice('error', this.safeMessage(error.message)); }
  }

  destroy() {
    this.closeModal();
    this.element = null;
  }
}

export function createActiveDirectoryPage(router) {
  return new ActiveDirectoryPage(router);
}
