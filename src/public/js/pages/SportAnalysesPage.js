import { listSportAnalyses } from '../services/sportApi.js?v=6';

const TYPE_LABELS = {
  morning: { emoji: '🌅', label: 'Matin' },
  evening: { emoji: '🌙', label: 'Soir' },
  activity: { emoji: '🏃', label: 'Sortie' },
};

export class SportAnalysesPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.data = null;
    this.loading = false;
    this.error = false;
  }

  async initialize() {
    this.loading = true;
    this.error = false;
    try {
      this.data = await listSportAnalyses(30);
    } catch (error) {
      this.error = true;
      this.data = null;
      console.error('Erreur chargement analyses sportives:', error);
    } finally {
      this.loading = false;
    }
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content';
    this._renderContent();
    return this.element;
  }

  _renderContent() {
    if (!this.element) return;
    const items = this.data?.items || [];
    this.element.innerHTML = `
      <div class="page-header sport-dashboard-header">
        <div class="page-header-left">
          <span class="sport-kicker">FORGEAI SPORT</span>
          <h1>Analyses IA</h1>
          <p class="page-subtitle">Analyses automatiques : bilan du matin, bilan du soir et débrief des sorties synchronisées depuis Garmin.</p>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-secondary btn-sm" data-action="refresh">Actualiser</button>
        </div>
      </div>
      ${this.error ? '<div class="card" role="alert"><div class="card-body">Impossible de charger les analyses.</div></div>' : ''}
      ${!this.error && this.loading && !this.data ? '<div class="card"><div class="card-body">Chargement…</div></div>' : ''}
      ${!this.error && !this.loading && !items.length ? `
        <div class="card sport-card"><div class="card-body">${this._empty('Aucune analyse pour le moment', "Les analyses apparaissent automatiquement : chaque matin, chaque soir, puis 15 minutes après chaque synchronisation Garmin d'une activité terminée.")}</div></div>
      ` : ''}
      ${items.map(item => this._analysisCard(item)).join('')}
    `;
    this._bindEvents();
  }

  _analysisCard(item) {
    const type = TYPE_LABELS[item.analysis_type] || { emoji: '📊', label: item.analysis_type };
    const day = item.analysis_day ? new Date(`${item.analysis_day}T00:00:00`).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : '';
    return `
      <article class="card sport-card">
        <div class="card-header">
          <div>
            <span class="sport-eyebrow">${type.emoji} ANALYSE ${type.label.toUpperCase()}</span>
            <h2>${this._escape(item.title)}</h2>
          </div>
          <span class="text-muted">${this._escape(day)}</span>
        </div>
        <div class="card-body">
          ${item.summary ? `<p><strong>${this._escape(item.summary)}</strong></p>` : ''}
          <div class="sport-analysis-content">${this._renderMarkdown(item.content)}</div>
          <p class="text-muted sport-health-caption">Générée le ${new Date(item.generated_at).toLocaleString('fr-FR')}${item.model ? ` · ${this._escape(item.provider || '')} ${this._escape(item.model)}` : ''}</p>
        </div>
      </article>`;
  }

  _bindEvents() {
    this.element.querySelector('[data-action="refresh"]')?.addEventListener('click', async () => {
      await this.initialize();
      this._renderContent();
    });
  }

  _renderMarkdown(content) {
    if (!content) return '';
    // Conversion Markdown minimale et sûre : texte échappé avant tout balisage.
    const escaped = this._escape(content);
    const lines = escaped.split('\n');
    let html = '';
    let inList = false;
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('## ')) {
        if (inList) { html += '</ul>'; inList = false; }
        html += `<h3>${trimmed.slice(3)}</h3>`;
      } else if (trimmed.startsWith('### ')) {
        if (inList) { html += '</ul>'; inList = false; }
        html += `<h4>${trimmed.slice(4)}</h4>`;
      } else if (/^[-*] /.test(trimmed)) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${trimmed.slice(2)}</li>`;
      } else if (trimmed) {
        if (inList) { html += '</ul>'; inList = false; }
        html += `<p>${trimmed}</p>`;
      }
    }
    if (inList) html += '</ul>';
    return html;
  }

  _empty(title, message) {
    return `<div class="sport-empty"><span class="sport-empty-mark">○</span><strong>${title}</strong><p>${message}</p></div>`;
  }

  _escape(value) {
    const element = document.createElement('div');
    element.textContent = value ?? '';
    return element.innerHTML;
  }

  destroy() {
    this.element = null;
  }
}

export function createSportAnalysesPage(router) {
  return new SportAnalysesPage(router);
}
