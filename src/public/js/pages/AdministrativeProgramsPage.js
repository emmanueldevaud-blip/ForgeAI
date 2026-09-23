import { authStore } from '../stores/auth.js';
import { listVolunteers } from '../services/housingApi.js';
import {
  listAdministrativeCapabilities,
  createAdministrativeCapability,
  listVolunteerCapabilities,
  assignVolunteerCapability,
  deleteVolunteerCapability,
  listAdministrativeUnavailabilities,
  createAdministrativeUnavailability,
  deleteAdministrativeUnavailability,
  listAdministrativeProgramTypes,
  listAdministrativeRoles,
  listAdministrativeSessions,
  createAdministrativeSession,
  generateAdministrativeSession,
  validateAdministrativeSession,
  updateAdministrativeAssignment,
} from '../services/administrativeApi.js';

const MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

function volunteerName(volunteer) {
  return `${volunteer.last_name || ''} ${volunteer.first_name || ''}`.trim();
}

export class AdministrativeProgramsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    const today = new Date();
    this.year = today.getFullYear();
    this.month = today.getMonth() + 1;
    this.activeTab = 'programmes';
    this.programs = [];
    this.roles = [];
    this.sessions = [];
    this.capabilities = [];
    this.volunteers = [];
    this.volunteerCapabilities = new Map();
    this.unavailabilities = [];
  }

  async initialize() {
    await this.loadData();
  }

  async loadData() {
    const [programs, roles, sessions, capabilities, volunteers, unavailabilities] = await Promise.all([
      listAdministrativeProgramTypes(),
      listAdministrativeRoles(),
      listAdministrativeSessions(this.year, this.month),
      listAdministrativeCapabilities(),
      listVolunteers({ limit: 1000, is_active: true }),
      listAdministrativeUnavailabilities(),
    ]);
    this.programs = programs || [];
    this.roles = roles || [];
    this.sessions = sessions || [];
    this.capabilities = capabilities || [];
    this.volunteers = volunteers || [];
    this.unavailabilities = unavailabilities || [];
    await Promise.all(this.volunteers.map(async volunteer => {
      const links = await listVolunteerCapabilities(volunteer.id);
      this.volunteerCapabilities.set(volunteer.id, new Set((links || []).map(link => link.capability_id)));
    }));
    this.renderState();
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Programmes administratifs</h1>
          <p class="page-subtitle">Génération et suivi des programmes des volontaires</p>
        </div>
      </div>
      <div class="admin-tabs" role="tablist">
        ${[['programmes', 'Programmes'], ['capacites', 'Capacités'], ['indisponibilites', 'Indisponibilités'], ['configuration', 'Configuration'], ['historique', 'Historique']].map(([id, label]) => `<button class="admin-tab ${id === this.activeTab ? 'admin-tab--active' : ''}" data-admin-tab="${id}">${label}</button>`).join('')}
      </div>
      <div data-admin-content></div>
    `;
    this.element.querySelectorAll('[data-admin-tab]').forEach(button => button.addEventListener('click', () => {
      this.activeTab = button.dataset.adminTab;
      this.renderState();
    }));
    this.renderState();
    return this.element;
  }

  renderState() {
    const container = this.element?.querySelector('[data-admin-content]');
    if (!container) return;
    this.element.querySelectorAll('[data-admin-tab]').forEach(button => button.classList.toggle('admin-tab--active', button.dataset.adminTab === this.activeTab));
    if (this.activeTab === 'programmes') this._renderPrograms(container);
    if (this.activeTab === 'capacites') this._renderCapabilities(container);
    if (this.activeTab === 'indisponibilites') this._renderUnavailabilities(container);
    if (this.activeTab === 'configuration') this._renderConfiguration(container);
    if (this.activeTab === 'historique') this._renderHistory(container);
  }

  _renderPrograms(container) {
    container.innerHTML = `
      <section class="card" style="padding:20px;margin-bottom:16px;">
        <div style="display:flex;gap:12px;align-items:end;flex-wrap:wrap;">
          <label>Mois <input type="month" data-month value="${this.year}-${String(this.month).padStart(2, '0')}" class="form-control"></label>
          <div style="flex:1;min-width:260px;">
            <label>Programmes à générer</label>
            <div style="display:flex;gap:14px;flex-wrap:wrap;">${this.programs.map(program => `<label><input type="checkbox" data-program-id="${program.id}" checked> ${escapeHtml(program.name)}</label>`).join('')}</div>
          </div>
          <button class="btn btn-primary" data-action="generate">Générer les programmes</button>
        </div>
      </section>
      <section class="card" style="padding:20px;">
        <h2 style="margin-top:0;">${MONTHS[this.month - 1]} ${this.year}</h2>
        ${this.sessions.length ? this.sessions.map(session => this._sessionHtml(session)).join('') : '<p>Aucun programme généré pour ce mois.</p>'}
      </section>
    `;
    container.querySelector('[data-month]')?.addEventListener('change', async event => {
      [this.year, this.month] = event.target.value.split('-').map(Number);
      await this.loadData();
    });
    container.querySelector('[data-action="generate"]')?.addEventListener('click', () => this._generateSelected(container));
    container.querySelectorAll('[data-action="generate-session"]').forEach(button => button.addEventListener('click', async () => {
      const result = await generateAdministrativeSession(Number(button.dataset.id));
      await this.loadData();
      if (result.conflicts?.length) alert(`Programme généré avec alertes :\n${result.conflicts.join('\n')}`);
    }));
    container.querySelectorAll('[data-action="validate"]').forEach(button => button.addEventListener('click', () => this._validate(Number(button.dataset.id))));
    container.querySelectorAll('[data-assignment]').forEach(select => select.addEventListener('change', () => this._updateAssignment(select)));
  }

  _sessionHtml(session) {
    const program = this.programs.find(item => item.id === session.program_type_id);
    const roleById = new Map(this.roles.map(role => [role.id, role]));
    const volunteerById = new Map(this.volunteers.map(volunteer => [volunteer.id, volunteer]));
    const assignments = [...(session.assignments || [])].sort((a, b) => String(a.scheduled_date).localeCompare(String(b.scheduled_date)));
    const conflicts = session._conflicts || [];
    return `<article style="padding:16px 0;border-bottom:1px solid var(--color-border-light);">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap;"><div><strong>${escapeHtml(program?.name || 'Programme')}</strong> <span class="status-badge">${escapeHtml(session.status)}</span></div><div style="display:flex;gap:8px;"><button class="btn btn-secondary btn-sm" data-action="generate-session" data-id="${session.id}">Régénérer</button><button class="btn btn-primary btn-sm" data-action="validate" data-id="${session.id}">Valider</button></div></div>
      ${conflicts.length ? `<div style="color:var(--color-danger);margin:10px 0;">${conflicts.map(escapeHtml).join('<br>')}</div>` : ''}
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:8px;margin-top:12px;">${assignments.map(assignment => {
        const role = roleById.get(assignment.role_type_id);
        const options = this.volunteers.filter(volunteer => this._compatible(volunteer.id, role?.required_capability_id, assignment.scheduled_date));
        return `<label style="display:grid;gap:4px;font-size:12px;"><span>${escapeHtml(assignment.scheduled_date)} · ${escapeHtml(role?.name || 'Rôle')}</span><select class="form-control" data-assignment="${assignment.id}"><option value="">Non affecté</option>${options.map(volunteer => `<option value="${volunteer.id}" ${volunteer.id === assignment.volunteer_id ? 'selected' : ''}>${escapeHtml(volunteerName(volunteer))}</option>`).join('')}</select></label>`;
      }).join('')}</div>
    </article>`;
  }

  _compatible(volunteerId, capabilityId, scheduledDate) {
    if (capabilityId && !this.volunteerCapabilities.get(volunteerId)?.has(capabilityId)) return false;
    return !this.unavailabilities.some(item => item.volunteer_id === volunteerId && item.starts_on <= scheduledDate && item.ends_on >= scheduledDate);
  }

  async _generateSelected(container) {
    const selected = [...container.querySelectorAll('[data-program-id]:checked')].map(input => Number(input.dataset.programId));
    const messages = [];
    for (const programId of selected) {
      let session = this.sessions.find(item => item.program_type_id === programId);
      if (!session) session = await createAdministrativeSession({ program_type_id: programId, year: this.year, month: this.month });
      const result = await generateAdministrativeSession(session.id);
      if (result.conflicts?.length) messages.push(`${this.programs.find(item => item.id === programId)?.name}: ${result.conflicts.join(', ')}`);
    }
    await this.loadData();
    alert(messages.length ? `Programmes générés avec alertes :\n${messages.join('\n')}` : 'Programmes générés. Vous pouvez les contrôler avant validation.');
  }

  async _validate(id) {
    const result = await validateAdministrativeSession(id);
    if (!result.valid) alert(`Validation impossible :\n${result.conflicts.join('\n')}`);
    else { alert('Programme validé.'); await this.loadData(); }
  }

  async _updateAssignment(select) {
    if (!select.value) return;
    try { await updateAdministrativeAssignment(Number(select.dataset.assignment), { volunteer_id: Number(select.value) }); await this.loadData(); }
    catch (error) { alert(error?.data?.detail || error.message || 'Affectation impossible'); await this.loadData(); }
  }

  _renderCapabilities(container) {
    container.innerHTML = `<section class="card" style="padding:20px;overflow:auto;"><h2 style="margin-top:0;">Capacités des volontaires</h2><p>Cochez les fonctions autorisées pour chaque volontaire.</p><table class="planning-table"><thead><tr><th>Volontaire</th>${this.capabilities.map(capability => `<th>${escapeHtml(capability.name)}</th>`).join('')}</tr></thead><tbody>${this.volunteers.map(volunteer => `<tr><th>${escapeHtml(volunteerName(volunteer))}</th>${this.capabilities.map(capability => `<td style="text-align:center;"><input type="checkbox" data-capability-volunteer="${volunteer.id}" data-capability="${capability.id}" ${this.volunteerCapabilities.get(volunteer.id)?.has(capability.id) ? 'checked' : ''}></td>`).join('')}</tr>`).join('')}</tbody></table></section>`;
    container.querySelectorAll('[data-capability-volunteer]').forEach(input => input.addEventListener('change', () => this._toggleCapability(input)));
  }

  async _toggleCapability(input) {
    const volunteerId = Number(input.dataset.capabilityVolunteer);
    const capabilityId = Number(input.dataset.capability);
    try {
      if (input.checked) await assignVolunteerCapability(volunteerId, { capability_id: capabilityId });
      else await deleteVolunteerCapability(volunteerId, capabilityId);
      const set = this.volunteerCapabilities.get(volunteerId) || new Set();
      input.checked ? set.add(capabilityId) : set.delete(capabilityId);
      this.volunteerCapabilities.set(volunteerId, set);
    } catch (error) { input.checked = !input.checked; alert(error?.data?.detail || error.message || 'Modification impossible'); }
  }

  _renderUnavailabilities(container) {
    container.innerHTML = `<section class="card" style="padding:20px;max-width:900px;"><h2 style="margin-top:0;">Indisponibilités</h2><form data-unavailability-form style="display:flex;gap:8px;flex-wrap:wrap;align-items:end;margin-bottom:18px;"><label>Volontaire<select name="volunteer_id" class="form-control" required><option value="">Choisir</option>${this.volunteers.map(volunteer => `<option value="${volunteer.id}">${escapeHtml(volunteerName(volunteer))}</option>`).join('')}</select></label><label>Du<input name="starts_on" type="date" class="form-control" required></label><label>Au<input name="ends_on" type="date" class="form-control" required></label><label>Motif<input name="reason" class="form-control"></label><button class="btn btn-primary">Ajouter</button></form><div>${this.unavailabilities.map(item => `<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--color-border-light);"><span>${escapeHtml(volunteerName(this.volunteers.find(volunteer => volunteer.id === item.volunteer_id) || {}))} · ${item.starts_on} → ${item.ends_on}${item.reason ? ` · ${escapeHtml(item.reason)}` : ''}</span><button class="btn btn-danger btn-sm" data-delete-unavailability="${item.id}">Supprimer</button></div>`).join('')}</div></section>`;
    container.querySelector('[data-unavailability-form]')?.addEventListener('submit', async event => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target)); data.volunteer_id = Number(data.volunteer_id); await createAdministrativeUnavailability(data); await this.loadData(); this.activeTab = 'indisponibilites'; this.renderState(); });
    container.querySelectorAll('[data-delete-unavailability]').forEach(button => button.addEventListener('click', async () => { await deleteAdministrativeUnavailability(Number(button.dataset.deleteUnavailability)); await this.loadData(); }));
  }

  _renderConfiguration(container) {
    container.innerHTML = `<section class="card" style="padding:20px;"><h2 style="margin-top:0;">Configuration des programmes</h2><form data-capability-form style="display:flex;gap:8px;align-items:end;flex-wrap:wrap;margin-bottom:18px;"><label>Code<input name="code" class="form-control" required placeholder="nouvelle_fonction"></label><label>Nom<input name="name" class="form-control" required placeholder="Nouvelle fonction"></label><button class="btn btn-primary">Ajouter une capacité</button></form>${this.programs.map(program => `<article style="padding:12px 0;border-bottom:1px solid var(--color-border-light);"><strong>${escapeHtml(program.name)}</strong><div>${program.frequency === 'weekly' ? 'Hebdomadaire' : escapeHtml(program.frequency)} · ${['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'][program.weekday]} · intervalle ${program.interval} semaine(s)</div><ul>${this.roles.filter(role => role.program_type_id === program.id).map(role => `<li>${escapeHtml(role.name)}${role.is_optional ? ' (facultatif)' : ''}</li>`).join('')}</ul></article>`).join('')}</section>`;
    container.querySelector('[data-capability-form]')?.addEventListener('submit', async event => {
      event.preventDefault();
      try {
        await createAdministrativeCapability(Object.fromEntries(new FormData(event.target)));
        await this.loadData();
        this.activeTab = 'configuration';
        this.renderState();
      } catch (error) { alert(error?.data?.detail || error.message || 'Création impossible'); }
    });
  }

  _renderHistory(container) {
    const assignments = this.sessions.flatMap(session => (session.assignments || []).map(assignment => ({ ...assignment, program: this.programs.find(program => program.id === session.program_type_id)?.name, volunteer: volunteerName(this.volunteers.find(volunteer => volunteer.id === assignment.volunteer_id) || {}) })));
    container.innerHTML = `<section class="card" style="padding:20px;overflow:auto;"><h2 style="margin-top:0;">Historique des participations</h2><table class="planning-table"><thead><tr><th>Date</th><th>Volontaire</th><th>Programme</th><th>Rôle</th><th>Statut</th></tr></thead><tbody>${assignments.map(assignment => `<tr><td>${assignment.scheduled_date}</td><td>${escapeHtml(assignment.volunteer)}</td><td>${escapeHtml(assignment.program)}</td><td>${escapeHtml(this.roles.find(role => role.id === assignment.role_type_id)?.name || '')}</td><td>${escapeHtml(assignment.status)}</td></tr>`).join('') || '<tr><td colspan="5">Aucune participation pour ce mois.</td></tr>'}</tbody></table></section>`;
  }
}

export function createAdministrativeProgramsPage(router) {
  return new AdministrativeProgramsPage(router);
}
