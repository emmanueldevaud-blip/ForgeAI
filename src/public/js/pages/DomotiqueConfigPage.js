import { authStore } from '../stores/auth.js';
import {
  createDomotiqueProfile,
  deleteDomotiqueProfile,
  getDomotiqueConfig,
  listDomotiqueProfiles,
  testDomotiqueConnection,
  updateDomotiqueConfig,
  updateDomotiqueOutput,
  updateDomotiqueProfile,
  updateDomotiqueSensor,
} from '../services/domotiqueApi.js?v=2';

const OUTPUT_ROLES = [
  { value: 'heater', label: 'Chauffage' },
  { value: 'cooler', label: 'Refroidissement' },
  { value: 'fan', label: 'Ventilation' },
  { value: 'humidifier', label: 'Humidificateur' },
  { value: 'dehumidifier', label: 'Déshumidificateur' },
  { value: 'other', label: 'Autre' },
];

const EXIT_CONDITIONS = [
  { value: 'time', label: 'Durée' },
  { value: 'weight', label: 'Perte de poids' },
  { value: 'manual', label: 'Manuelle' },
];

const EMPTY_PHASE = () => ({
  order: 1,
  name: 'Nouvelle phase',
  target_temperature: null,
  target_humidity: null,
  tolerance_temperature: 1,
  tolerance_humidity: 2,
  min_duration_hours: null,
  max_duration_hours: null,
  weight_loss_target_pct: null,
  exit_condition: 'time',
});

export class DomotiqueConfigPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.config = null;
    this.profiles = [];
    this.selectedProfileId = null;
    this.draftProfile = null;
    this.testResult = null;
    this.message = '';
    this.error = null;
  }

  get canConfigure() {
    return authStore.hasPermission('domotique.configure');
  }

  async initialize() {
    if (!this.canConfigure) return;
    this.error = null;
    try {
      this.config = await getDomotiqueConfig();
      this.profiles = (await listDomotiqueProfiles()).profiles || [];
      if (this.profiles.length && this.selectedProfileId == null) {
        this.selectedProfileId = this.profiles[0].id;
        this._loadDraft();
      }
    } catch (error) {
      this.error = error;
    }
  }

  _loadDraft() {
    const profile = this.profiles.find((item) => item.id === this.selectedProfileId);
    if (!profile) {
      this.draftProfile = null;
      return;
    }
    this.draftProfile = JSON.parse(JSON.stringify(profile));
    this.draftProfile.phases = (profile.phases || []).map((phase) => ({ ...phase }));
  }

  render(options = {}) {
    if (options.embedded !== undefined) this.embedded = Boolean(options.embedded);
    const previous = this.element;
    this.element = document.createElement('div');
    this.element.className = this.embedded ? 'domo-config-embedded' : 'page-content domo-page';
    this._renderContent();
    this._bindEvents();
    if (previous && previous !== this.element && previous.isConnected) {
      previous.replaceWith(this.element);
    }
    return this.element;
  }

  _header(title) {
    if (this.embedded) return '';
    return `
      <div class="page-header">
        <div class="page-header-left"><span class="domo-kicker">DOMOTIQUE</span><h1>${title}</h1></div>
      </div>`;
  }

  _renderContent() {
    if (!this.canConfigure) {
      this.element.innerHTML = `
        ${this._header('Configuration')}
        <div class="card"><div class="card-body"><p class="text-muted">Permission « domotique.configure » requise.</p></div></div>`;
      return;
    }
    if (this.error) {
      this.element.innerHTML = `
        ${this._header('Configuration')}
        <div class="card" role="alert"><div class="card-body"><p>Erreur : ${this._escape(this.error.message || 'inconnue')}</p></div></div>`;
      return;
    }
    const config = this.config || {};
    this.element.innerHTML = `
      ${this._header('Configuration de la cave')}
      ${this.message ? `<div class="domo-flash">${this._escape(this.message)}</div>` : ''}
      <div class="domo-config-grid">
        ${this._connectionCard(config)}
        ${this._thresholdsCard(config)}
        ${this._coolerCard(config)}
        ${this._sensorsCard(config)}
        ${this._outputsCard(config)}
      </div>
      ${this._profilesSection()}`;
  }

  // ------------------------------------------------------------------ #

  _connectionCard(config) {
    const address = this._splitBaseUrl(config.base_url);
    const passwordPlaceholder = config.has_api_password ? '(inchangé)' : '';
    return `
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">CONNEXION</span><h2>Raspberry Pi</h2></div></div>
        <div class="card-body">
          <form data-connection-form class="domo-form--2">
            <label>Adresse IP
              <input class="form-control" name="ip" type="text" placeholder="192.168.1.82" value="${this._escape(address.ip)}" required>
            </label>
            <label>Port
              <input class="form-control" name="port" type="number" min="1" max="65535" placeholder="8080" value="${this._escape(address.port)}">
            </label>
            <label>Utilisateur
              <input class="form-control" name="api_user" type="text" autocomplete="username" value="${this._escape(config.api_user || '')}">
            </label>
            <label>Mot de passe
              <input class="form-control" name="api_password" type="password" autocomplete="new-password" placeholder="${passwordPlaceholder}">
            </label>
            <label>Fréquence de récupération (s)
              <input class="form-control" name="poll_interval_s" type="number" min="5" max="600" value="${config.poll_interval_s || 30}">
            </label>
            <div class="domo-actions domo-span">
              <button class="btn btn-primary" type="submit">Enregistrer</button>
              <button class="btn btn-secondary" type="button" data-action="test-connection">Tester la connexion</button>
            </div>
          </form>
          <div data-test-result>${this._testResultHtml()}</div>
          <p class="text-muted"><small>API attendue : GET /state · POST /command · GET /health. Les identifiants sont envoyés en Basic Auth (mot de passe jamais renvoyé par l'API).</small></p>
        </div>
      </section>`;
  }

  _testResultHtml() {
    const test = this.testResult;
    if (!test) return '';
    return `<p class="domo-test ${test.ok ? 'is-ok' : 'is-ko'}">${this._escape(test.message)}${test.state ? ` · T° ${this._num(test.state.temperature)} · HR ${this._num(test.state.humidity)}` : ''}</p>`;
  }

  _splitBaseUrl(base) {
    if (!base) return { ip: '', port: '' };
    try {
      const url = new URL(base);
      return { ip: url.hostname, port: url.port };
    } catch {
      return { ip: String(base).replace(/^https?:\/\//, '').split('/')[0], port: '' };
    }
  }

  _buildBaseUrl(ip, port) {
    const raw = String(ip || '').trim();
    if (!raw) return '';
    if (raw.includes('://')) return raw.replace(/\/+$/, '');
    const suffix = String(port || '').trim() ? `:${String(port).trim()}` : '';
    return `http://${raw.replace(/\/+$/, '')}${suffix}`;
  }

  _thresholdsCard(config) {
    const values = config.config || {};
    return `
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">SÉCURITÉ</span><h2>Seuils d’alerte</h2></div></div>
        <div class="card-body">
          <form data-thresholds-form class="domo-form--2">
            <label>Température min (°C)<input class="form-control" name="temp_min" type="number" step="0.1" value="${values.temp_min ?? 5}"></label>
            <label>Température max (°C)<input class="form-control" name="temp_max" type="number" step="0.1" value="${values.temp_max ?? 30}"></label>
            <label>Humidité min (% HR)<input class="form-control" name="hum_min" type="number" step="0.1" value="${values.hum_min ?? 40}"></label>
            <label>Humidité max (% HR)<input class="form-control" name="hum_max" type="number" step="0.1" value="${values.hum_max ?? 99}"></label>
            <label>Anti-spam alertes (min)<input class="form-control" name="alert_cooldown_min" type="number" min="1" value="${values.alert_cooldown_min ?? 30}"></label>
            <label>Données obsolètes après (s)<input class="form-control" name="obsolete_after_s" type="number" min="15" value="${values.obsolete_after_s ?? 90}"></label>
            <label>Rétention historique (jours)<input class="form-control" name="retention_days" type="number" min="7" value="${values.retention_days ?? 90}"></label>
            <div class="domo-actions"><button class="btn btn-primary" type="submit">Enregistrer</button></div>
          </form>
          <p class="text-muted"><small>Notifications envoyées aux utilisateurs ayant la permission « domotique.view ».</small></p>
        </div>
      </section>`;
  }

  _coolerCard(config) {
    const values = config.config || {};
    return `
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">COMPRESSEUR</span><h2>Anti-court-cycle</h2></div></div>
        <div class="card-body">
          <form data-cooler-form class="domo-form--2">
            <label>Délai minimum entre 2 cycles (s)
              <input class="form-control" name="cooler_min_off_s" type="number" min="0" max="3600" value="${values.cooler_min_off_s ?? 180}">
            </label>
            <label>Durée minimum de marche (s)
              <input class="form-control" name="cooler_min_on_s" type="number" min="0" max="3600" value="${values.cooler_min_on_s ?? 120}">
            </label>
            <div class="domo-actions domo-span"><button class="btn btn-primary" type="submit">Enregistrer</button></div>
          </form>
          <p class="text-muted"><small>Le compresseur du froid ne démarre pas avant le délai minimum et reste allumé au minimum la durée indiquée : évite les cycles courts.</small></p>
        </div>
      </section>`;
  }

  _sensorsCard(config) {
    const sensors = config.sensors || [];
    const rows = sensors.map((sensor) => `
      <div class="domo-config-row" data-sensor-row="${sensor.id}">
        <strong>${this._escape(sensor.name)}</strong>
        <span class="text-muted">${this._escape(sensor.key)} · ${this._escape(sensor.unit || '—')}</span>
        <label class="domo-check">
          <input type="checkbox" data-sensor-enabled="${sensor.id}" ${sensor.enabled ? 'checked' : ''}> Actif
        </label>
      </div>`).join('');
    return `
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">CAPTEURS</span><h2>Sondes</h2></div></div>
        <div class="card-body">
          <p class="text-muted">Température et humidité proviennent de la sonde I2C du Raspberry. La balance peut être activée si elle est raccordée.</p>
          ${rows || '<p class="text-muted">Aucun capteur.</p>'}
        </div>
      </section>`;
  }

  _outputsCard(config) {
    const outputs = config.outputs || [];
    const rows = outputs.map((output) => `
      <div class="domo-config-row" data-output-row="${output.id}">
        <strong>GPIO ${output.index}</strong>
        <input class="form-control" data-output-name="${output.id}" value="${this._escape(output.name)}" maxlength="100">
        <select class="form-control" data-output-role="${output.id}">
          ${OUTPUT_ROLES.map((role) => `<option value="${role.value}" ${output.role === role.value ? 'selected' : ''}>${role.label}</option>`).join('')}
        </select>
        <button class="btn btn-sm btn-secondary" type="button" data-output-save="${output.id}">Enregistrer</button>
      </div>`).join('');
    return `
      <section class="card domo-card">
        <div class="card-header"><div><span class="domo-eyebrow">ACTIONNEURS</span><h2>8 sorties GPIO</h2></div></div>
        <div class="card-body">
          <p class="text-muted">Le rôle détermine la régulation automatique (chauffage, refroidissement, humidification, déshumidification). « Ventilation » et « Autre » restent en pilotage manuel.</p>
          ${rows || '<p class="text-muted">Aucune sortie.</p>'}
        </div>
      </section>`;
  }

  // ------------------------------------------------------------------ #
  // Profils / phases
  // ------------------------------------------------------------------ //

  _profilesSection() {
    const options = this.profiles.map((profile) => `
      <option value="${profile.id}" ${profile.id === this.selectedProfileId ? 'selected' : ''}>${this._escape(profile.name)}${profile.is_system ? ' (système)' : ''}</option>`).join('');
    const draft = this.draftProfile;
    return `
      <section class="card domo-card domo-profiles">
        <div class="card-header">
          <div><span class="domo-eyebrow">PROFILS</span><h2>Profils de séchage</h2></div>
          <div class="domo-actions">
            <select class="form-control" data-profile-select>${options}</select>
            <button class="btn btn-secondary" type="button" data-action="new-profile">Nouveau profil</button>
          </div>
        </div>
        <div class="card-body">
          ${draft ? this._profileEditor(draft) : '<p class="text-muted">Aucun profil.</p>'}
        </div>
      </section>`;
  }

  _profileEditor(draft) {
    const phases = (draft.phases || []).map((phase, index) => `
      <tr data-phase-row="${index}">
        <td><input class="form-control" data-phase-field="order" data-phase-index="${index}" type="number" min="1" value="${phase.order}"></td>
        <td><input class="form-control" data-phase-field="name" data-phase-index="${index}" value="${this._escape(phase.name)}"></td>
        <td><input class="form-control" data-phase-field="target_temperature" data-phase-index="${index}" type="number" step="0.1" value="${phase.target_temperature ?? ''}"></td>
        <td><input class="form-control" data-phase-field="target_humidity" data-phase-index="${index}" type="number" step="0.1" value="${phase.target_humidity ?? ''}"></td>
        <td><input class="form-control" data-phase-field="tolerance_temperature" data-phase-index="${index}" type="number" step="0.1" value="${phase.tolerance_temperature ?? ''}"></td>
        <td><input class="form-control" data-phase-field="tolerance_humidity" data-phase-index="${index}" type="number" step="0.1" value="${phase.tolerance_humidity ?? ''}"></td>
        <td><input class="form-control" data-phase-field="min_duration_hours" data-phase-index="${index}" type="number" step="1" value="${phase.min_duration_hours ?? ''}"></td>
        <td><input class="form-control" data-phase-field="max_duration_hours" data-phase-index="${index}" type="number" step="1" value="${phase.max_duration_hours ?? ''}"></td>
        <td><input class="form-control" data-phase-field="weight_loss_target_pct" data-phase-index="${index}" type="number" step="0.1" value="${phase.weight_loss_target_pct ?? ''}"></td>
        <td>
          <select class="form-control" data-phase-field="exit_condition" data-phase-index="${index}">
            ${EXIT_CONDITIONS.map((exit) => `<option value="${exit.value}" ${phase.exit_condition === exit.value ? 'selected' : ''}>${exit.label}</option>`).join('')}
          </select>
        </td>
        <td><button class="btn btn-sm btn-secondary" type="button" data-phase-remove="${index}">✕</button></td>
      </tr>`).join('');
    return `
      <form data-profile-form>
        <div class="domo-form--2">
          <label>Code<input class="form-control" name="code" value="${this._escape(draft.code)}" pattern="[a-z0-9-]+" required></label>
          <label>Nom<input class="form-control" name="name" value="${this._escape(draft.name)}" required></label>
          <label>Objectif perte (%)<input class="form-control" name="target_weight_loss_pct" type="number" step="0.1" value="${draft.target_weight_loss_pct ?? ''}"></label>
          <label>Plage min (%)<input class="form-control" name="weight_loss_min_pct" type="number" step="0.1" value="${draft.weight_loss_min_pct ?? ''}"></label>
          <label>Plage max (%)<input class="form-control" name="weight_loss_max_pct" type="number" step="0.1" value="${draft.weight_loss_max_pct ?? ''}"></label>
          <label class="domo-span">Description<input class="form-control" name="description" value="${this._escape(draft.description || '')}"></label>
        </div>
        <div class="domo-table-wrap">
          <table class="domo-table">
            <thead>
              <tr>
                <th>#</th><th>Nom</th><th>Target °C</th><th>Target %HR</th><th>Tol °C</th><th>Tol %HR</th>
                <th>Min h</th><th>Max h</th><th>Perte cible %</th><th>Transition</th><th></th>
              </tr>
            </thead>
            <tbody>${phases}</tbody>
          </table>
        </div>
        <div class="domo-actions">
          <button class="btn btn-primary" type="submit">Enregistrer le profil</button>
          <button class="btn btn-secondary" type="button" data-action="add-phase">Ajouter une phase</button>
          ${draft.is_system ? '' : '<button class="btn btn-danger" type="button" data-action="delete-profile">Supprimer</button>'}
        </div>
        <small class="text-muted">Transition « Durée » : passage à la phase suivante après la durée maximale. « Perte de poids » : lorsque le seuil de perte est atteint (laisser vide pour transition manuelle). « Manuelle » : passage via le bouton « Phase suivante » du cycle.</small>
      </form>`;
  }

  // ------------------------------------------------------------------ #
  // Événements
  // ------------------------------------------------------------------ #

  _bindEvents() {
    if (!this.element) return;

    const connectionForm = this.element.querySelector('[data-connection-form]');
    if (connectionForm) {
      connectionForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const data = new FormData(connectionForm);
        const payload = {
          base_url: this._buildBaseUrl(data.get('ip'), data.get('port')),
          poll_interval_s: Number(data.get('poll_interval_s')) || 30,
          api_user: String(data.get('api_user') || '').trim(),
        };
        const password = String(data.get('api_password') || '');
        if (password) payload.api_password = password;
        try {
          await updateDomotiqueConfig(payload);
          this.message = 'Connexion enregistrée.';
          this.config = await getDomotiqueConfig();
        } catch (error) {
          this.message = error.message || 'Échec de l’enregistrement.';
        }
        this.render();
      });
    }

    const testButton = this.element.querySelector('[data-action="test-connection"]');
    if (testButton) {
      testButton.addEventListener('click', async () => {
        const data = new FormData(connectionForm);
        const payload = {
          base_url: this._buildBaseUrl(data.get('ip'), data.get('port')),
          api_user: String(data.get('api_user') || '').trim(),
        };
        const password = String(data.get('api_password') || '');
        if (password) payload.api_password = password;
        testButton.disabled = true;
        this.testResult = await testDomotiqueConnection(payload).catch((error) => ({
          ok: false, message: error.message || 'Test impossible',
        }));
        const resultBox = this.element.querySelector('[data-test-result]');
        if (resultBox) resultBox.innerHTML = this._testResultHtml();
        testButton.disabled = false;
      });
    }

    const thresholdsForm = this.element.querySelector('[data-thresholds-form]');
    if (thresholdsForm) {
      thresholdsForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const data = new FormData(thresholdsForm);
        try {
          await updateDomotiqueConfig({
            temp_min: Number(data.get('temp_min')),
            temp_max: Number(data.get('temp_max')),
            hum_min: Number(data.get('hum_min')),
            hum_max: Number(data.get('hum_max')),
            alert_cooldown_min: Number(data.get('alert_cooldown_min')),
            obsolete_after_s: Number(data.get('obsolete_after_s')),
            retention_days: Number(data.get('retention_days')),
          });
          this.message = 'Seuils enregistrés.';
          this.config = await getDomotiqueConfig();
        } catch (error) {
          this.message = error.message || 'Échec de l’enregistrement.';
        }
        this.render();
      });
    }

    const coolerForm = this.element.querySelector('[data-cooler-form]');
    if (coolerForm) {
      coolerForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const data = new FormData(coolerForm);
        try {
          await updateDomotiqueConfig({
            cooler_min_off_s: Number(data.get('cooler_min_off_s')),
            cooler_min_on_s: Number(data.get('cooler_min_on_s')),
          });
          this.message = 'Réglages compresseur enregistrés.';
          this.config = await getDomotiqueConfig();
        } catch (error) {
          this.message = error.message || 'Échec de l’enregistrement.';
        }
        this.render();
      });
    }

    this.element.querySelectorAll('[data-sensor-enabled]').forEach((checkbox) => {
      checkbox.addEventListener('change', async () => {
        const id = Number(checkbox.dataset.sensorEnabled);
        try {
          await updateDomotiqueSensor(id, { enabled: checkbox.checked });
          this.message = 'Capteur mis à jour.';
          this.config = await getDomotiqueConfig();
        } catch (error) {
          this.message = error.message || 'Échec.';
        }
        this.render();
      });
    });

    this.element.querySelectorAll('[data-output-save]').forEach((button) => {
      button.addEventListener('click', async () => {
        const id = Number(button.dataset.outputSave);
        const nameInput = this.element.querySelector(`[data-output-name="${id}"]`);
        const roleSelect = this.element.querySelector(`[data-output-role="${id}"]`);
        try {
          await updateDomotiqueOutput(id, { name: nameInput.value, role: roleSelect.value });
          this.message = 'Sortie mise à jour.';
          this.config = await getDomotiqueConfig();
        } catch (error) {
          this.message = error.message || 'Échec.';
        }
        this.render();
      });
    });

    const profileSelect = this.element.querySelector('[data-profile-select]');
    if (profileSelect) {
      profileSelect.addEventListener('change', () => {
        this.selectedProfileId = Number(profileSelect.value);
        this._loadDraft();
        this.render();
      });
    }

    const newProfileButton = this.element.querySelector('[data-action="new-profile"]');
    if (newProfileButton) {
      newProfileButton.addEventListener('click', () => {
        this.selectedProfileId = null;
        this.draftProfile = {
          id: null,
          code: 'nouveau-profil',
          name: 'Nouveau profil',
          description: '',
          target_weight_loss_pct: 38,
          weight_loss_min_pct: 35,
          weight_loss_max_pct: 40,
          is_system: false,
          phases: [{ ...EMPTY_PHASE(), id: null }],
        };
        this.render();
      });
    }

    const addPhaseButton = this.element.querySelector('[data-action="add-phase"]');
    if (addPhaseButton) {
      addPhaseButton.addEventListener('click', () => {
        this._syncDraftFromForm();
        const order = (this.draftProfile.phases.length || 0) + 1;
        this.draftProfile.phases.push({ ...EMPTY_PHASE(), id: null, order });
        this.render();
      });
    }

    this.element.querySelectorAll('[data-phase-remove]').forEach((button) => {
      button.addEventListener('click', () => {
        this._syncDraftFromForm();
        const index = Number(button.dataset.phaseRemove);
        this.draftProfile.phases.splice(index, 1);
        this.draftProfile.phases.forEach((phase, position) => { phase.order = position + 1; });
        this.render();
      });
    });

    const profileForm = this.element.querySelector('[data-profile-form]');
    if (profileForm) {
      profileForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        this._syncDraftFromForm();
        const draft = this.draftProfile;
        const payload = {
          code: draft.code,
          name: draft.name,
          description: draft.description || null,
          target_weight_loss_pct: draft.target_weight_loss_pct,
          weight_loss_min_pct: draft.weight_loss_min_pct,
          weight_loss_max_pct: draft.weight_loss_max_pct,
          phases: draft.phases.map((phase) => ({
            id: phase.id ?? null,
            order: Number(phase.order),
            name: phase.name,
            target_temperature: phase.target_temperature,
            target_humidity: phase.target_humidity,
            tolerance_temperature: phase.tolerance_temperature,
            tolerance_humidity: phase.tolerance_humidity,
            min_duration_hours: phase.min_duration_hours,
            max_duration_hours: phase.max_duration_hours,
            weight_loss_target_pct: phase.weight_loss_target_pct,
            exit_condition: phase.exit_condition,
          })),
        };
        try {
          if (draft.id) {
            await updateDomotiqueProfile(draft.id, payload);
            this.message = 'Profil mis à jour.';
          } else {
            const created = await createDomotiqueProfile(payload);
            this.selectedProfileId = created.id;
            this.message = 'Profil créé.';
          }
          this.profiles = (await listDomotiqueProfiles()).profiles || [];
          this._loadDraft();
        } catch (error) {
          this.message = error.message || 'Échec de l’enregistrement du profil.';
        }
        this.render();
      });
    }

    const deleteButton = this.element.querySelector('[data-action="delete-profile"]');
    if (deleteButton) {
      deleteButton.addEventListener('click', async () => {
        if (!this.draftProfile?.id) return;
        try {
          await deleteDomotiqueProfile(this.draftProfile.id);
          this.message = 'Profil supprimé.';
          this.selectedProfileId = null;
          this.draftProfile = null;
          this.profiles = (await listDomotiqueProfiles()).profiles || [];
          if (this.profiles.length) {
            this.selectedProfileId = this.profiles[0].id;
            this._loadDraft();
          }
        } catch (error) {
          this.message = error.message || 'Suppression impossible.';
        }
        this.render();
      });
    }
  }

  _syncDraftFromForm() {
    const form = this.element?.querySelector('[data-profile-form]');
    if (!form || !this.draftProfile) return;
    const data = new FormData(form);
    this.draftProfile.code = String(data.get('code') || this.draftProfile.code);
    this.draftProfile.name = String(data.get('name') || this.draftProfile.name);
    this.draftProfile.description = String(data.get('description') || '');
    const numeric = (key) => {
      const raw = data.get(key);
      if (raw === '' || raw == null) return null;
      const value = Number(raw);
      return Number.isNaN(value) ? null : value;
    };
    this.draftProfile.target_weight_loss_pct = numeric('target_weight_loss_pct');
    this.draftProfile.weight_loss_min_pct = numeric('weight_loss_min_pct');
    this.draftProfile.weight_loss_max_pct = numeric('weight_loss_max_pct');
    this.element.querySelectorAll('[data-phase-field]').forEach((field) => {
      const index = Number(field.dataset.phaseIndex);
      const key = field.dataset.phaseField;
      const phase = this.draftProfile.phases[index];
      if (!phase) return;
      if (key === 'name' || key === 'exit_condition') {
        phase[key] = field.value;
      } else if (key === 'order') {
        phase.order = Number(field.value) || index + 1;
      } else {
        const value = field.value === '' ? null : Number(field.value);
        phase[key] = Number.isNaN(value) ? null : value;
      }
    });
  }

  // ------------------------------------------------------------------ #

  _escape(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  _num(value) {
    if (value == null || Number.isNaN(Number(value))) return '—';
    return Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 1 });
  }
}

export function createDomotiqueConfigPage(router) {
  return new DomotiqueConfigPage(router);
}
