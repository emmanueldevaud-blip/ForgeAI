/**
 * Analytics & Intelligence - Community Manager IA
 * Page d'analyse et d'intelligence des performances Facebook & Instagram.
 * Six espaces : Vue d'ensemble, Instagram, Facebook, Performance editoriale,
 * IA, Historique et rapports.
 */

import { api } from '../services/api.js';
import { authStore } from '../stores/auth.js';
import {
  getMetaOverview,
  getMetaInstagramAccount,
  getMetaInstagramMedia,
  getMetaInstagramMediaDetail,
  getMetaFacebookPage,
  getMetaFacebookPosts,
  getMetaPerformance,
  getMetaAudience,
  getMetaHistory,
  postMetaSync,
  getMetaSyncStatus,
  postMetaAiAnalyze,
  getMetaAiRecommendations,
  getMetaReport,
  postMetaRecommendationToCalendar,
} from '../services/sportApi.js?v=1';

const TABS = [
  { code: 'overview', label: 'Vue d\u2019ensemble', icon: 'dashboard' },
  { code: 'instagram', label: 'Instagram', icon: 'run' },
  { code: 'facebook', label: 'Facebook', icon: 'home' },
  { code: 'performance', label: 'Performance editoriale', icon: 'bar-chart' },
  { code: 'ai', label: 'Intelligence artificielle', icon: 'bot' },
  { code: 'history', label: 'Historique et rapports', icon: 'calendar-days' },
];

export class AnalyticsIntelligencePage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this.tab = 'overview';
    this.period = '30';
    this.loading = false;
    this.error = null;
    this.syncing = false;
    this.data = {
      overview: null,
      instagram: null,
      instagramMedia: [],
      facebook: null,
      facebookPosts: [],
      performance: null,
      audience: null,
      history: null,
      ai: null,
      recommendations: [],
      syncRuns: [],
    };
    this.canSync = false;
    this.canAnalyze = false;
    this.canReports = false;
  }

  async initialize() {
    try {
      await authStore.loadCurrentUser();
    } catch (e) {
      console.error('Erreur chargement utilisateur:', e);
    }
    this.canSync = authStore.hasPermission('meta_analytics.sync');
    this.canAnalyze = authStore.hasPermission('meta_analytics.analyze');
    this.canReports = authStore.hasPermission('meta_analytics.reports');
    await this._loadTab(this.tab);
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'page-content am-page';

    this.element.innerHTML = `
      <div class="page-header">
        <div>
          <h1>Analytics &amp; Intelligence</h1>
          <p class="page-subtitle">Performances Facebook et Instagram \u2014 Community Manager IA</p>
        </div>
        <div class="page-header-actions">
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:13px;color:#666;">P\u00e9riode</label>
            <select id="am-period" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd;background:#fff;">
              <option value="7">7 derniers jours</option>
              <option value="30" selected>30 derniers jours</option>
              <option value="90">90 derniers jours</option>
            </select>
          </div>
          ${this.canSync ? `
            <button class="btn btn-primary" id="am-sync-btn" title="Synchroniser maintenant">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
              </svg>
              Synchroniser
            </button>
          ` : ''}
          ${this.data.syncing ? `<span class="status-badge active" style="margin-left:8px;">Synchro\u2026</span>` : ''}
        </div>
      </div>

      ${this._renderAlert()}

      <nav class="am-tabs" role="tablist" aria-label="Espaces Analytics">
        ${TABS.map(t => `
          <button role="tab" aria-selected="${this.tab === t.code}" data-tab="${t.code}"
            class="am-tab ${this.tab === t.code ? 'am-tab--active' : ''}">
            ${t.label}
          </button>
        `).join('')}
      </nav>

      <div class="am-tab-panels">
        ${TABS.map(t => `
          <section role="tabpanel" id="am-panel-${t.code}" hidden="${this.tab !== t.code}">
            ${this._renderPanel(t.code)}
          </section>
        `).join('')}
      </div>
    `;

    this._bindEvents();
    return this.element;
  }

  _renderAlert() {
    if (this.error) {
      return `<div class="alert alert-error" style="margin:0 16px 16px;">${this._escape(this.error)}</div>`;
    }
    return '';
  }

  _renderPanel(code) {
    switch (code) {
      case 'overview': return this._renderOverview();
      case 'instagram': return this._renderInstagram();
      case 'facebook': return this._renderFacebook();
      case 'performance': return this._renderPerformance();
      case 'ai': return this._renderAI();
      case 'history': return this._renderHistory();
      default: return this._renderOverview();
    }
  }

  // ===================================================================== #
  // Vue d'ensemble
  // ===================================================================== #
  _renderOverview() {
    const o = this.data.overview;
    if (!o) return this._renderEmpty('Aucune donn\u00e9e de vue d\u2019ensemble. Cliquez sur Synchroniser.');

    const ig = o.instagram || {};
    const fb = o.facebook || {};
    const igMetrics = ig.metrics || {};
    const fbMetrics = fb.metrics || {};

    return `
      <div class="am-grid am-grid--kpis">
        ${this._kpi('Abonn\u00e9s Instagram', this._metricVal(igMetrics.followers_count), this._metricStat(igMetrics.followers_count))}
        ${this._kpi('Port\u00e9e', this._metricVal(igMetrics.reach || fbMetrics.page_impressions), this._metricStat(igMetrics.reach || fbMetrics.page_impressions))}
        ${this._kpi('Impressions', this._metricVal(igMetrics.impressions || fbMetrics.page_impressions), this._metricStat(igMetrics.impressions || fbMetrics.page_impressions))}
        ${this._kpi('Interactions', this._fmt((igMetrics.likes?.valeur||0)+(igMetrics.comments?.valeur||0)+(igMetrics.shares?.valeur||0)), 'available')}
        ${this._kpi('Comptes engag\u00e9s', this._metricVal(fbMetrics.page_engaged_users), this._metricStat(fbMetrics.page_engaged_users))}
        ${this._kpi('Taux engagement', this._metricVal(igMetrics.engagement_rate), this._metricStat(igMetrics.engagement_rate))}
      </div>

      <div class="am-grid am-grid--charts" style="margin-top:16px;">
        <div class="card">
          <div class="card-header"><div><span class="eyebrow">\u00c9volution (${o.periode.jours} jours)</span><p class="text-muted">Donn\u00e9es r\u00e9elles Meta Graph API</p></div></div>
          <div class="card-body" style="min-height:260px;">
            ${this._renderChartPlaceholder('historique')}
          </div>
        </div>
        <div class="card">
          <div class="card-header"><div><span class="eyebrow">Instagram vs Facebook</span><p class="text-muted">Comparaison des port\u00e9es</p></div></div>
          <div class="card-body" style="min-height:260px;">
            ${this._renderComparisonBar(ig, fb)}
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:16px;">
        <div class="card-header"><div><span class="eyebrow">\u00c9tat des donn\u00e9es</span><p class="text-muted">Derni\u00e8re synchro et disponibilit\u00e9</p></div></div>
        <div class="card-body">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div><strong>Derni\u00e8re synchronisation :</strong> ${o.date_derniere_synchronisation || 'Jamais'}</div>
              <div style="margin-top:4px;"><strong>Donn\u00e9es disponibles :</strong> <span class="status-badge ${o.donnees_disponibles ? 'active' : 'inactive'}">${o.donnees_disponibles ? 'Oui' : 'Non'}</span></div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:13px;color:#666;">Comptes configur\u00e9s</div>
              <div style="font-size:20px;font-weight:700;">${o.comptes.length}</div>
            </div>
          </div>
          <div style="margin-top:12px;">
            ${o.comptes.map(c => `
              <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f0f0;">
                <span>${c.account_name || c.platform_account_id} <span style="opacity:.7;">(${c.platform})</span></span>
                <span class="status-badge ${c.username ? 'active':'inactive'}">${c.username || 'Non connect\u00e9'}</span>
              </div>
            `).join('') || '<div style="color:#999;">Aucun compte Meta configur\u00e9.</div>'}
          </div>
          ${o.message ? `<div class="alert alert-error" style="margin-top:12px;">${this._escape(o.message)}</div>` : ''}
        </div>
      </div>
    `;
  }

  _kpi(label, value, status) {
    const disp = value === undefined || value === null ? 'Indisponible' : String(value);
    return `
      <div class="card am-kpi">
        <div class="card-body" style="padding:16px;">
          <div style="font-size:12px;color:#666;text-transform:uppercase;letter-spacing:.04em;">${label}</div>
          <div style="font-size:26px;font-weight:700;margin-top:6px;">${disp}</div>
          <div style="font-size:11px;color:#999;margin-top:2px;">${status === 'available' ? 'Donn\u00e9e r\u00e9elle' : 'Non disponible'}</div>
        </div>
      </div>
    `;
  }

  _renderComparisonBar(ig, fb) {
    const igReach = Number(ig.metrics?.reach?.valeur || 0);
    const fbReach = Number(fb.metrics?.page_impressions?.valeur || 0);
    const max = Math.max(igReach, fbReach, 1);
    return `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="width:120px;font-size:12px;">Instagram Port\u00e9e</span>
          <div class="am-bar" style="flex:1;"><div class="am-bar-fill" style="width:${Math.round(igReach/max*100)}%;background:#7c3aed;"></div></div>
          <span style="width:60px;font-size:12px;text-align:right;">${igReach.toLocaleString()}</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="width:120px;font-size:12px;">Facebook Port\u00e9e</span>
          <div class="am-bar" style="flex:1;"><div class="am-bar-fill" style="width:${Math.round(fbReach/max*100)}%;background:#1877f2;"></div></div>
          <span style="width:60px;font-size:12px;text-align:right;">${fbReach.toLocaleString()}</span>
        </div>
      </div>
    `;
  }

  _renderChartPlaceholder(kind) {
    return `<div class="am-empty" style="padding:40px;text-align:center;color:#999;">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin:0 auto 12px;opacity:.5;">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line>
      </svg>
      <div style="font-size:13px;">Graphique d\u2019\u00e9volution \u00e0 charger depuis l\u2019API</div>
    </div>`;
  }

  // ===================================================================== #
  // Instagram
  // ===================================================================== #
  async _renderInstagram() {
    if (this.data.instagram === null && !this.data.instagramMedia.length) {
      return this._renderEmpty('Aucune donn\u00e9e Instagram. Cliquez sur Synchroniser.');
    }
    const acct = this.data.instagram || {};
    const metrics = acct.metrics || {};
    return `
      <div class="am-grid am-grid--kpis">
        ${this._kpi('Abonn\u00e9s', metrics.followers_count?.valeur, metrics.followers_count?.statut)}
        ${this._kpi('Port\u00e9e', metrics.reach?.valeur, metrics.reach?.statut)}
        ${this._kpi('Impressions', metrics.impressions?.valeur, metrics.impressions?.statut)}
        ${this._kpi('Visites profil', metrics.profile_visits?.valeur, metrics.profile_visits?.statut)}
        ${this._kpi('Clics lien', metrics.website_clicks?.valeur, metrics.website_clicks?.statut)}
        ${this._kpi('Interactions', (metrics.likes?.valeur||0)+(metrics.comments?.valeur||0), 'available')}
      </div>

      <div class="card" style="margin-top:16px;">
        <div class="card-header"><div><span class="eyebrow">Contenus (Reels, carrousels, publications)</span><p class="text-muted">Performances individuelles</p></div></div>
        <div class="card-body" style="overflow-x:auto;">
          <table class="table">
            <thead><tr><th>M\u00e9dia</th><th>Type</th><th>Reach</th><th>Vues</th><th>Likes</th><th>Commentaires</th><th>Partages</th><th>Enregistrements</th><th>Taux engagement</th></tr></thead>
            <tbody>
              ${this.data.instagramMedia.map(m => `
                <tr>
                  <td><a href="${m.permalink || '#'}" target="_blank" rel="noopener" style="color:#1877f2;">${m.media_id}</a></td>
                  <td><span class="badge badge-secondary">${m.media_type || '-'}</span></td>
                  <td>${this._metricVal(m.metrics.reach)}</td>
                  <td>${this._metricVal(m.metrics.video_views)}</td>
                  <td>${this._metricVal(m.metrics.likes)}</td>
                  <td>${this._metricVal(m.metrics.comments)}</td>
                  <td>${this._metricVal(m.metrics.shares)}</td>
                  <td>${this._metricVal(m.metrics.saves)}</td>
                  <td>${this._pct(m.metrics.engagement_rate?.valeur)}</td>
                </tr>
              `).join('') || '<tr><td colspan="9" style="text-align:center;color:#999;padding:24px;">Aucun m\u00e9dia collect\u00e9.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ===================================================================== #
  // Facebook
  // ===================================================================== #
  async _renderFacebook() {
    if (this.data.facebook === null && !this.data.facebookPosts.length) {
      return this._renderEmpty('Aucune donn\u00e9e Facebook. La Page doit \u00eatre accessible via /me/accounts (jeton SUAT avec t\u00e2ches Page).');
    }
    const page = (this.data.facebook && this.data.facebook.pages && this.data.facebook.pages[0]) || {};
    const metrics = page.metrics || {};
    return `
      <div class="am-grid am-grid--kpis">
        ${this._kpi('Abonn\u00e9s Page', metrics.page_fans?.valeur, metrics.page_fans?.statut)}
        ${this._kpi('Port\u00e9e', metrics.page_impressions?.valeur, metrics.page_impressions?.statut)}
        ${this._kpi('Impressions organiques', metrics.page_impressions_organic?.valeur, metrics.page_impressions_organic?.statut)}
        ${this._kpi('Impressions payantes', metrics.page_impressions_paid?.valeur, metrics.page_impressions_paid?.statut)}
        ${this._kpi('Comptes engag\u00e9s', metrics.page_engaged_users?.valeur, metrics.page_engaged_users?.statut)}
        ${this._kpi('Clics', metrics.page_link_clicks_total?.valeur, metrics.page_link_clicks_total?.statut)}
      </div>

      <div class="card" style="margin-top:16px;">
        <div class="card-header"><div><span class="eyebrow">Publications Facebook</span><p class="text-muted">D\u00e9tail par publication</p></div></div>
        <div class="card-body" style="overflow-x:auto;">
          <table class="table">
            <thead><tr><th>Publication</th><th>Type</th><th>Date</th><th>Likes</th><th>Commentaires</th><th>Partages</th><th>Permalien</th></tr></thead>
            <tbody>
              ${this.data.facebookPosts.map(p => `
                <tr>
                  <td>${this._escape(p.caption || '') || p.media_id}</td>
                  <td><span class="badge badge-secondary">${p.type || '-'}</span></td>
                  <td>${p.created_at || '-'}</td>
                  <td>${this._metricVal(p.metrics.likes)}</td>
                  <td>${this._metricVal(p.metrics.comments)}</td>
                  <td>${this._metricVal(p.metrics.shares)}</td>
                  <td><a href="${p.permalink || '#'}" target="_blank" rel="noopener" style="color:#1877f2;font-size:12px;">Voir</a></td>
                </tr>
              `).join('') || '<tr><td colspan="7" style="text-align:center;color:#999;padding:24px;">Aucune publication collect\u00e9e.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ===================================================================== #
  // Performance editoriale
  // ===================================================================== #
  async _renderPerformance() {
    const perf = this.data.performance;
    if (!perf || !perf.data) return this._renderEmpty('Aucune performance editoriale calcul\u00e9e.');

    const d = perf.data;
    return `
      <div class="card" style="margin-bottom:16px;">
        <div class="card-header"><div><span class="eyebrow">Score de performance editoriale (sur 100)</span><p class="text-muted">Ponderation configurable : portee 20%, engagement 20%, partage/sauvegarde 25%, video 20%, croissance 15%.</p></div></div>
        <div class="card-body">
          <div style="display:flex;gap:16px;align-items:flex-start;">
            <div style="flex:1;">
              <div style="font-size:48px;font-weight:800;">${d.meilleur_score ? d.meilleur_score.score : '-'}</div>
              <div style="color:#666;">Meilleur contenu</div>
            </div>
            <div style="font-size:13px;color:#666;line-height:1.6;">
              <div><strong>Pond\u00e9ration :</strong></div>
              <div>Portee relative 20% | Taux engagement 20%</div>
              <div>Partages/Enregistrements 25% | Video 20% | Croissance 15%</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><div><span class="eyebrow">Classement des contenus</span><p class="text-muted">Comparaison de contenus de format et anciennet\u00e9 comparables.</p></div></div>
        <div class="card-body" style="overflow-x:auto;">
          <table class="table">
            <thead><tr><th>Score</th><th>M\u00e9dia</th><th>Type</th><th>Portee</th><th>Interactions</th><th>Partages</th><th>Enregistrements</th></tr></thead>
            <tbody>
              ${(d.medias || []).slice(0, 10).map(m => `
                <tr>
                  <td><span class="badge badge-${m.score >= 70 ? 'active' : m.score >= 40 ? 'warning' : 'inactive'}">${m.score}</span></td>
                  <td>${m.media_id}</td>
                  <td>${m.media_type || '-'}</td>
                  <td>${this._fmt(m.indicators.reach)}</td>
                  <td>${this._fmt(m.indicators.interactions)}</td>
                  <td>${this._fmt(m.indicators.amplification)}</td>
                  <td>${this._fmt(m.indicators.video_views)}</td>
                </tr>
              `).join('') || '<tr><td colspan="7" style="text-align:center;color:#999;padding:24px;">Aucun contenu \u00e0 scorer.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // ===================================================================== #
  // IA
  // ===================================================================== #
  async _renderAI() {
    return `
      <div class="card" style="margin-bottom:16px;">
        <div class="card-header"><div><span class="eyebrow">Analyse IA editoriale</span><p class="text-muted">Utilise le routage IA existant de ForgeAI (aucune donn\u00e9e invent\u00e9e).</p></div></div>
        <div class="card-body">
          <div class="form-actions" style="gap:8px;">
            ${this.canAnalyze ? `<button class="btn btn-primary" id="am-ai-analyze">Lancer l\u2019analyse IA</button>` : `<span class="text-muted">Permission meta_analytics.analyze requise</span>`}
            ${this.data.ai?.loading ? `<span class="status-badge active">Analyse en cours\u2026</span>` : ''}
          </div>
          ${this.data.ai?.error ? `<div class="alert alert-error" style="margin-top:12px;">${this._escape(this.data.ai.error)}</div>` : ''}
          ${this.data.ai?.data ? this._renderAIResult(this.data.ai.data) : `<div class="am-empty" style="padding:24px;text-align:center;color:#999;">Aucune analyse IA lanc\u00e9e.</div>`}
        </div>
      </div>

      <div class="card">
        <div class="card-header"><div><span class="eyebrow">Recommandations IA</span><p class="text-muted">Id\u00e9es de publication, Reels, carrousels, l\u00e9gendes, hashtags.</p></div></div>
        <div class="card-body" style="overflow-x:auto;">
          <table class="table">
            <thead><tr><th>Type</th><th>Titre</th><th>Justification</th><th>Confiance</th><th>Statut</th><th>Action</th></tr></thead>
            <tbody>
              ${this.data.recommendations.map(r => `
                <tr>
                  <td>${this._escape(r.type)}</td>
                  <td><strong>${this._escape(r.titre)}</strong></td>
                  <td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${this._escape(r.justification || '')}</td>
                  <td><span class="badge badge-${r.confiance === 'eleve' ? 'active' : r.confiance === 'moyen' ? 'warning' : 'inactive'}">${r.confiance || '-'}</span></td>
                  <td>${this._escape(r.statut)}</td>
                  <td>
                    <button class="btn btn-sm btn-secondary" data-am-action="calendar" data-am-rec-id="${r.id}">Ajouter au calendrier</button>
                    <button class="btn btn-sm btn-secondary" data-am-action="studio" data-am-rec-id="${r.id}">Envoyer au Studio</button>
                    <button class="btn btn-sm btn-secondary" data-am-action="idea" data-am-rec-id="${r.id}">Id\u00e9e</button>
                  </td>
                </tr>
              `).join('') || '<tr><td colspan="6" style="text-align:center;color:#999;padding:24px;">Aucune recommandation IA.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  _renderAIResult(analysis) {
    const period = analysis.periode || {};
    return `
      <div style="background:#f8fafc;border-radius:8px;padding:16px;">
        <div style="font-size:12px;color:#666;text-transform:uppercase;">P\u00e9riode: ${period.debut} -> ${period.fin}</div>
        <div style="margin-top:8px;"><strong>Bilan :</strong> ${this._escape(String(analysis.bilan || '')).slice(0, 600)}</div>
        ${analysis.tendances ? `<div style="margin-top:8px;"><strong>Tendances :</strong> ${this._escape(String(analysis.tendances)).slice(0, 400)}</div>` : ''}
        ${analysis.recommandations_calendrier ? `<div style="margin-top:8px;"><strong>Calendrier :</strong> ${this._escape(String(analysis.recommandations_calendrier)).slice(0, 400)}</div>` : ''}
      </div>
    `;
  }

  // ===================================================================== #
  // Historique et rapports
  // ===================================================================== #
  async _renderHistory() {
    return `
      <div class="card" style="margin-bottom:16px;">
        <div class="card-header"><div><span class="eyebrow">Historique des synchronisations</span><p class="text-muted">Traces d'ex\u00e9cution, erreurs et relances.</p></div></div>
        <div class="card-body" style="overflow-x:auto;">
          <table class="table">
            <thead><tr><th>Plateforme</th><th>Statut</th><th>D\u00e9but</th><th>Fin</th><th>Comptes</th><th>Metriques</th><th>Erreur</th></tr></thead>
            <tbody>
              ${this.data.syncRuns.map(r => `
                <tr>
                  <td>${r.platform}</td>
                  <td><span class="badge badge-${r.status === 'completed' ? 'active' : r.status === 'partial' ? 'warning' : 'danger'}">${r.status}</span></td>
                  <td>${r.started_at || '-'}</td>
                  <td>${r.finished_at || '-'}</td>
                  <td>${r.accounts_processed}</td>
                  <td>${r.metrics_collected}</td>
                  <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${this._escape(r.error_message || '-')}</td>
                </tr>
              `).join('') || '<tr><td colspan="7" style="text-align:center;color:#999;padding:24px;">Aucune synchronisation enregistr\u00e9e.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><div><span class="eyebrow">G\u00e9n\u00e9ration de rapports</span><p class="text-muted">Export PDF ou CSV de la synthese, Instagram, Facebook, audience et recommandations IA.</p></div></div>
        <div class="card-body">
          <div class="form-actions" style="gap:8px;flex-wrap:wrap;">
            ${this.canReports ? `
              <button class="btn btn-primary" id="am-export-pdf">Exporter PDF</button>
              <button class="btn btn-secondary" id="am-export-csv">Exporter CSV</button>
            ` : `<span class="text-muted">Permission meta_analytics.reports requise</span>`}
            <label style="font-size:13px;color:#666; margin-left:8px;">P\u00e9riode:</label>
            <select id="am-report-period" style="padding:6px 10px;border-radius:6px;border:1px solid #ddd;">
              <option value="30">30 derniers jours</option>
              <option value="90">90 derniers jours</option>
            </select>
          </div>
          <div class="am-empty" style="padding:16px;text-align:center;color:#999;">
            Le rapport contient : synthese generale, Instagram, Facebook, evolution de l\u2019audience, performances editoriales, meilleurs contenus, contenus \u00e0 am\u00e9liorer, recommandations IA et comparaison avec la periode precedente.
          </div>
        </div>
      </div>
    `;
  }

  _renderEmpty(message) {
    return `<div class="card"><div class="card-body" style="text-align:center;padding:48px;color:#999;">
      <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin:0 auto 16px;opacity:.4;">
        <circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="16"></line><line x1="12" y1="18" x2="12.01" y2="18"></line>
      </svg>
      <div>${this._escape(message)}</div>
    </div></div>`;
  }

  _fmt(v) { return v === undefined || v === null ? '-' : Number(v).toLocaleString(); }
  _metricVal(m) { if (!m || typeof m !== 'object') return this._fmt(m); return this._fmt(m.valeur); }
  _metricStat(m) { return m && m.statut ? m.statut : 'unavailable'; }
  _pct(v) { return v === undefined || v === null ? '-' : Number(v).toFixed(2) + '%'; }
  _escape(t) { if (t == null) return ''; return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  // ===================================================================== #
  // Chargement / actions
  // ===================================================================== #
  async _loadTab(code) {
    this.tab = code;
    this.loading = true;
    this._refreshContent();
    try {
      switch (code) {
        case 'overview': await this._loadOverview(); break;
        case 'instagram': await this._loadInstagram(); break;
        case 'facebook': await this._loadFacebook(); break;
        case 'performance': await this._loadPerformance(); break;
        case 'ai': await this._loadAI(); break;
        case 'history': await this._loadHistory(); break;
      }
    } catch (e) {
      this.error = e?.data?.detail || e?.message || 'Erreur de chargement';
      console.error('Erreur chargement onglet:', e);
    } finally {
      this.loading = false;
      this._refreshContent();
    }
  }

  _refreshContent() {
    if (!this.element) return;
    const panel = this.element.querySelector(`#am-panel-${this.tab}`);
    if (panel) panel.innerHTML = this._renderPanel(this.tab);
    this._bindPanelEvents(this.tab);
  }

  _bindEvents() {
    // Period selector
    const periodSel = this.element.querySelector('#am-period');
    if (periodSel) {
      periodSel.value = this.period;
      periodSel.addEventListener('change', (e) => {
        this.period = e.target.value;
        this._loadTab(this.tab);
      });
    }

    // Sync button
    const syncBtn = this.element.querySelector('#am-sync-btn');
    if (syncBtn) {
      syncBtn.addEventListener('click', () => this._doSync());
    }

    // Tabs
    this.element.querySelectorAll('[data-tab]').forEach(btn => {
      btn.addEventListener('click', () => this._loadTab(btn.dataset.tab));
    });

    this._bindPanelEvents(this.tab);
  }

  _bindPanelEvents(code) {
    const panel = this.element.querySelector(`#am-panel-${code}`);
    if (!panel) return;

    if (code === 'ai') {
      const analyzeBtn = panel.querySelector('#am-ai-analyze');
      if (analyzeBtn) analyzeBtn.addEventListener('click', () => this._doAiAnalyze());
      panel.querySelectorAll('[data-am-action]').forEach(btn => {
        btn.addEventListener('click', () => {
          const action = btn.dataset.amAction;
          const recId = btn.dataset.amRecId;
          this._handleAiAction(action, recId);
        });
      });
    }

    if (code === 'history') {
      panel.querySelector('#am-export-pdf')?.addEventListener('click', () => this._doExport('pdf'));
      panel.querySelector('#am-export-csv')?.addEventListener('click', () => this._doExport('csv'));
    }
  }

  async _loadOverview() {
    this.data.overview = await getMetaOverview(this.period);
  }

  async _loadInstagram() {
    const [acct, media] = await Promise.all([
      getMetaInstagramAccount().catch(() => null),
      getMetaInstagramMedia().catch(() => null),
    ]);
    this.data.instagram = acct?.data || null;
    this.data.instagramMedia = media?.data?.medias || [];
  }

  async _loadFacebook() {
    const [page, posts] = await Promise.all([
      getMetaFacebookPage().catch(() => null),
      getMetaFacebookPosts().catch(() => null),
    ]);
    this.data.facebook = page?.data || null;
    this.data.facebookPosts = posts?.data?.posts || [];
  }

  async _loadPerformance() {
    this.data.performance = await getMetaPerformance().catch(() => null);
  }

  async _loadAI() {
    if (!this.canAnalyze) return;
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - 30);
    const fmt = (d) => d.toISOString().slice(0, 10);
    this.data.ai = { loading: true };
    this._refreshContent();
    try {
      const res = await postMetaAiAnalyze(fmt(start), fmt(today));
      this.data.ai = { loading: false, data: res.data || res };
    } catch (e) {
      this.data.ai = { loading: false, error: e?.data?.detail || e?.message };
    }
    this._refreshContent();
    await this._loadRecommendations();
  }

  async _loadRecommendations() {
    try {
      const res = await getMetaAiRecommendations();
      this.data.recommendations = res?.data?.recommandations || [];
    } catch (e) {
      this.data.recommendations = [];
    }
    if (this.tab === 'ai') this._refreshContent();
  }

  async _loadHistory() {
    const [runs] = await Promise.all([getMetaSyncStatus().catch(() => null)]);
    this.data.syncRuns = runs?.data?.sync_runs || [];
  }

  async _doSync() {
    this.syncing = true;
    this.error = null;
    this._refreshContent();
    try {
      const res = await postMetaSync();
      this.data.syncing = false;
      await this._loadOverview();
      await this._loadHistory();
    } catch (e) {
      this.syncing = false;
      this.error = e?.data?.detail || e?.message || 'Synchronisation echouee';
      console.error('Synchro echec:', e);
    } finally {
      this._refreshContent();
    }
  }

  async _doAiAnalyze() {
    await this._loadAI();
  }

  async _handleAiAction(action, recId) {
    if (action === 'calendar') {
      try {
        const res = await postMetaRecommendationToCalendar(recId);
        this.error = null;
        await this._loadRecommendations();
        this.router.navigate(`/community-manager?recId=${recId}&source=meta_analytics`);
      } catch (e) {
        this.error = e?.data?.detail || e?.message || 'Ajout au calendrier echoue';
        this._refreshContent();
      }
    } else if (action === 'studio') {
      this.router.navigate(`/community-manager?recId=${recId}&source=meta_analytics`);
    } else if (action === 'idea') {
      this.router.navigate(`/community-manager?recId=${recId}&source=meta_analytics`);
    }
  }

  async _doExport(format) {
    const reportPeriodEl = this.element.querySelector('#am-report-period');
    const days = reportPeriodEl ? reportPeriodEl.value : '30';
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - Number(days));
    const fmt = (d) => d.toISOString().slice(0, 10);
    try {
      const arrayBuffer = await getMetaReport(format, fmt(start), fmt(today));
      const mimeType = format === 'pdf' ? 'application/pdf' : 'text/csv;charset=utf-8';
      const blob = new Blob([arrayBuffer], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `rapport_meta_analytics_${fmt(start)}_${fmt(today)}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      this.error = e?.data?.detail || e?.message || 'Export echoue';
      console.error('Export echec:', e);
    }
  }
}

export function createAnalyticsIntelligencePage(router) {
  return new AnalyticsIntelligencePage(router);
}
