import { analyzeSportActivity, listSportActivities } from '../services/sportApi.js?v=2';

export class SportActivitiesPage {
  constructor() { this.element = null; this.items = []; this.loading = true; this.error = null; }

  async initialize() {
    this.loading = true;
    this.error = null;
    try { this.items = (await listSportActivities({ page_size: 100 })).items || []; }
    catch (error) { this.error = error; }
    finally { this.loading = false; }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this.element.innerHTML = `
      <div class="page-header"><div><h1>Activités sportives</h1><p class="page-subtitle">Historique normalisé des activités importées.</p></div></div>
      <div class="card"><div class="card-body"><div class="table-container"><table class="data-table"><thead><tr><th>Date</th><th>Sport</th><th>Distance</th><th>Durée</th><th>D+</th><th>Source</th></tr></thead><tbody>
        ${this.loading ? '<tr class="table-loading" role="status"><td colspan="7">Chargement des activités...</td></tr>' : this.error ? '<tr class="table-error" role="alert"><td colspan="7">Impossible de charger les activités.</td></tr>' : this.items.length ? this.items.map(item => `<tr><td>${new Date(item.started_at).toLocaleString('fr-FR')}</td><td>${this._escape(item.activity_name || item.sport_type)}</td><td>${item.distance_m == null ? '-' : `${(item.distance_m / 1000).toFixed(2)} km`}</td><td>${this._duration(item.duration_seconds)}</td><td>${item.elevation_gain_m == null ? '-' : `${Math.round(item.elevation_gain_m)} m`}</td><td>${this._escape(item.source_type)}</td><td><button class="btn btn-sm btn-secondary" data-analyze="${item.id}">Analyser</button></td></tr><tr class="sport-analysis-row" data-result="${item.id}" hidden><td colspan="7"></td></tr>`).join('') : '<tr><td colspan="7">Aucune activité.</td></tr>'}
      </tbody></table></div></div></div>`;
    this.element.querySelectorAll('[data-analyze]').forEach(button => button.addEventListener('click', () => this._analyze(button)));
    return this.element;
  }

  async _analyze(button) {
    const result = this.element.querySelector(`[data-result="${button.dataset.analyze}"]`);
    button.disabled = true;
    result.hidden = false;
    result.querySelector('td').textContent = 'Analyse en cours...';
    try {
      const analysis = await analyzeSportActivity(button.dataset.analyze);
      const observations = analysis.observations?.length ? analysis.observations.join(' ') : 'Aucun point remarquable calculable.';
      const drift = analysis.cardiac_drift ? ` Dérive cardiaque calculée : ${analysis.cardiac_drift.percent}%.` : '';
      const ai = analysis.ai_analysis;
      const aiText = ai?.status === 'available' && ai.result?.answer
        ? ` Analyse IA : ${ai.result.answer}`
        : ai?.status === 'pending'
          ? ' Analyse IA en cours, recharge cette analyse dans quelques instants.'
          : ai?.status === 'unavailable'
            ? ' Analyse IA temporairement indisponible; les calculs déterministes restent disponibles.'
            : '';
      result.querySelector('td').textContent = `${observations}${drift}${aiText}`;
    } catch (error) {
      result.querySelector('td').textContent = 'Analyse indisponible pour cette activité.';
    } finally {
      button.disabled = false;
    }
  }

  _duration(seconds) { return `${Math.floor((seconds || 0) / 3600)}h ${String(Math.floor(((seconds || 0) % 3600) / 60)).padStart(2, '0')}min`; }
  _escape(value) { const el = document.createElement('div'); el.textContent = value || ''; return el.innerHTML; }
}

export function createSportActivitiesPage() { return new SportActivitiesPage(); }
