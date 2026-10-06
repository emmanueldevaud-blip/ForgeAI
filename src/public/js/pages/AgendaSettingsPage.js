import { authStore } from '../stores/auth.js';
import {
  getAgendaGroups,
  getAgendaSettings,
  updateAgendaSettings,
} from '../services/agendaApi.js?v=2';

const GROUP_SOURCE_LABELS = {
  ad: 'Active Directory',
  local: 'Local',
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[char]));
}

export class AgendaSettingsPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.groups = [];
    this.groupIds = [];
    this.message = '';
    this.error = null;
  }

  get canManage() {
    return authStore.hasPermission('agenda.manage');
  }

  async initialize() {
    if (!this.canManage) return;
    this.error = null;
    this.message = '';
    try {
      const settings = await getAgendaSettings();
      this.groupIds = settings?.planning_group_ids || [];
    } catch (error) {
      console.error('[agenda-settings] échec GET /agenda/settings:', error);
      this.error = error;
      return;
    }
    try {
      const groupsResponse = await getAgendaGroups();
      if (!groupsResponse || !Array.isArray(groupsResponse.groups)) {
        console.error('[agenda-settings] réponse inattendue GET /agenda/groups:', groupsResponse);
        this.error = new Error('Réponse inattendue du serveur pour la liste des groupes.');
        this.groups = [];
        return;
      }
      this.groups = groupsResponse.groups;
    } catch (error) {
      console.error('[agenda-settings] échec GET /agenda/groups:', error);
      this.error = error;
      this.groups = [];
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content agenda-page';
    this.renderState();
    return this.element;
  }

  destroy() {
    if (this.element) this.element.remove();
    this.element = null;
  }

  renderState() {
    if (!this.element) return;
    this.element.innerHTML = `
      <div class="page-header">
        <div class="page-header-left">
          <h1>Paramètres de l’agenda</h1>
          <p class="page-subtitle">Groupes affichés dans le planning par bureau.</p>
        </div>
        <div class="page-header-right">
          <button type="button" class="btn btn-secondary btn-sm" data-action="back">← Planning</button>
        </div>
      </div>
      ${this._bodyHtml()}
    `;
    this._bind();
  }

  _bodyHtml() {
    if (!this.canManage) {
      return `
        <div class="card">
          <div class="card-body agenda-empty">
            <h2>Accès refusé</h2>
            <p>La permission « agenda.manage » est requise pour configurer l’agenda.</p>
          </div>
        </div>`;
    }

    if (this.error) {
      return `
        <div class="card" role="alert">
          <div class="card-body agenda-empty">
            <h2>Impossible de charger les paramètres</h2>
            <p>${escapeHtml(this.error.message || 'Erreur inconnue')}</p>
            <button class="btn btn-primary" data-action="retry">Réessayer</button>
          </div>
        </div>`;
    }

    const selected = new Set(this.groupIds.map(Number));
    const rows = this.groups.length
      ? this.groups.map(group => `
          <label class="agenda-check agenda-settings-group">
            <input type="checkbox" name="planning_group" value="${group.id}" ${selected.has(group.id) ? 'checked' : ''}>
            <span>
              <strong>${escapeHtml(group.description || group.name)}</strong>
              <span class="agenda-room-meta">${escapeHtml(GROUP_SOURCE_LABELS[group.source] || group.source)} · ${group.user_count} membre${group.user_count > 1 ? 's' : ''}</span>
            </span>
          </label>`).join('')
      : '<p class="agenda-none">Aucun groupe disponible.</p>';

    return `
      <section class="card agenda-section">
        <header class="agenda-section-header">
          <div>
            <h2>Groupes du planning</h2>
            <p class="agenda-section-desc">
              Cochez les groupes dont les membres apparaissent dans le planning par bureau,
              même sans présence renseignée. Les personnes déjà inscrites restent toujours visibles.
            </p>
          </div>
        </header>
        <form data-agenda-settings-form class="card-body agenda-section-body">
          <div class="agenda-settings-groups">${rows}</div>
          <div class="form-actions">
            <button class="btn btn-primary" type="submit">Enregistrer</button>
            <span data-settings-message role="status">${escapeHtml(this.message)}</span>
          </div>
        </form>
      </section>`;
  }

  _bind() {
    this.element.querySelector('[data-action="back"]')?.addEventListener('click', () => {
      this.router.navigate('/agenda');
    });
    this.element.querySelector('[data-action="retry"]')?.addEventListener('click', async () => {
      await this.initialize();
      this.renderState();
    });

    const form = this.element.querySelector('[data-agenda-settings-form]');
    form?.addEventListener('submit', async event => {
      event.preventDefault();
      const groupIds = [...form.querySelectorAll('input[name="planning_group"]:checked')]
        .map(input => Number(input.value));
      const submit = form.querySelector('button[type="submit"]');
      if (submit) submit.disabled = true;
      try {
        const settings = await updateAgendaSettings(groupIds);
        this.groupIds = settings?.planning_group_ids || groupIds;
        this.message = 'Paramètres enregistrés.';
      } catch (error) {
        this.message = error.message || 'Échec de l’enregistrement.';
      } finally {
        if (submit) submit.disabled = false;
      }
      this.renderState();
    });
  }
}

export function createAgendaSettingsPage(router) {
  return new AgendaSettingsPage(router);
}
