import { getAiSettings, updateAiSettings } from '../services/adminApi.js?v=2';

export class AiSettingsPage {
  constructor() {
    this.element = null;
    this.settings = null;
  }

  async initialize() {
    this.settings = await getAiSettings();
  }

  // ------------------------------------------------------------------ #
  // Infobulle intégrée au label
  // ------------------------------------------------------------------ #

  _label(text, tooltip, inputHtml) {
    const tip = tooltip ? ` data-tooltip="${tooltip}"` : '';
    return `<label${tip}><span>${text}</span>${inputHtml}</label>`;
  }

  _check(name, text, tooltip) {
    const tip = tooltip ? ` data-tooltip="${tooltip}"` : '';
    return `<label class="checkbox-label"${tip}><input name="${name}" type="checkbox"> ${text}</label>`;
  }

  // ------------------------------------------------------------------ #
  // Carte fournisseur
  // ------------------------------------------------------------------ #

  _providerCard(prefix, title, tooltip) {
    return `
      <div class="card ai-provider-card">
        <div class="card-header">
          <h2>${title}</h2>
          <label class="checkbox-label ai-provider-toggle" data-tooltip="${tooltip}">
            <input name="${prefix}_enabled" type="checkbox"> Activé
          </label>
        </div>
        <div class="card-body ai-provider-body">
          <div class="form-row">
            ${this._label('Clé API', 'Clé secrète du fournisseur. Laisser vide si déjà enregistrée.',
              `<input name="${prefix}_api_key" type="password" autocomplete="new-password" placeholder="Non configurée">`)}
            ${this._label('Modèle', 'Modèle à utiliser. Laisser vide pour le modèle par défaut du fournisseur.',
              `<input name="${prefix}_model" maxlength="100" placeholder="Catalogue par défaut">`)}
          </div>
          <div class="form-row">
            <label><span>Statut de la clé</span><span class="text-muted" data-key-status="${prefix}"></span></label>
            ${this._label('URL de base', 'URL de l’API du fournisseur (ne modifier que si le fournisseur change d’endpoint).',
              `<input name="${prefix}_base_url" maxlength="255">`)}
          </div>
        </div>
      </div>
    `;
  }

  _updateKeyStatuses() {
    const form = this.element.querySelector('[data-ai-form]');
    if (!form) return;
    ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
      const configured = !!this.settings?.[prefix]?.api_key_configured;
      const input = form.elements[`${prefix}_api_key`];
      const status = this.element.querySelector(`[data-key-status="${prefix}"]`);
      if (input) {
        input.placeholder = configured
          ? 'Clé configurée — laisser vide pour conserver'
          : 'Non configurée';
      }
      if (status) {
        status.textContent = configured
          ? '✓ Clé enregistrée (masquée pour sécurité)'
          : 'Aucune clé enregistrée';
        status.classList.toggle('text-success', configured);
      }
    });
    // Web Search (Brave)
    const wsConfigured = !!this.settings?.web_search_api_key_configured;
    const wsInput = form.elements['web_search_api_key'];
    const wsStatus = this.element.querySelector('[data-key-status="web_search"]');
    if (wsInput) {
      wsInput.placeholder = wsConfigured
        ? 'Clé configurée — laisser vide pour conserver'
        : 'Non configurée';
    }
    if (wsStatus) {
      wsStatus.textContent = wsConfigured
        ? '✓ Clé enregistrée (masquée pour sécurité)'
        : 'Aucune clé enregistrée';
      wsStatus.classList.toggle('text-success', wsConfigured);
    }
  }

  _setMessage(text) {
    this.element.querySelectorAll('[data-ai-message]').forEach((el) => {
      el.textContent = text;
    });
  }

  // ------------------------------------------------------------------ #
  // Liaison du formulaire
  // ------------------------------------------------------------------ #

  _bindSettingsForm() {
    const form = this.element.querySelector('[data-ai-form]');
    if (!form) return;
    const s = this.settings || {};

    const setValue = (name, value) => { form.elements[name].value = value ?? ''; };
    form.elements.enabled.checked = s.enabled !== false;
    form.elements.default_provider.value = s.default_provider || 'auto';
    setValue('default_model', s.default_model || 'auto');
    setValue('provider_order', s.provider_order || 'groq,gemini,openrouter');
    setValue('timeout_seconds', s.timeout_seconds ?? 30);
    setValue('max_retries', s.max_retries ?? 2);
    setValue('retry_backoff_seconds', s.retry_backoff_seconds ?? 1);
    form.elements.ai_router_enabled.checked = s.ai_router_enabled !== false;
    form.elements.ai_router_prefer_free.checked = s.ai_router_prefer_free !== false;
    setValue('ai_router_cooldown_seconds', s.ai_router_cooldown_seconds ?? 300);
    form.elements.web_search_enabled.checked = s.web_search_enabled !== false;
    form.elements.web_search_provider.value = s.web_search_provider || 'brave';
    setValue('web_search_max_results', s.web_search_max_results ?? 8);
    setValue('web_search_timeout_seconds', s.web_search_timeout_seconds ?? 15);
    form.elements.web_search_fallback_enabled.checked = s.web_search_fallback_enabled !== false;
    form.elements.web_search_cache_enabled.checked = s.web_search_cache_enabled !== false;
    setValue('web_search_cache_ttl_seconds', s.web_search_cache_ttl_seconds ?? 3600);
    ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
      form.elements[`${prefix}_enabled`].checked = s[prefix]?.enabled !== false;
      setValue(`${prefix}_model`, s[prefix]?.model);
      setValue(`${prefix}_base_url`, s[prefix]?.base_url);
    });
    this._updateKeyStatuses();

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitBtn = form.querySelector('[type="submit"]');
      if (submitBtn?.disabled) return;
      if (submitBtn) submitBtn.disabled = true;
      const providerPayload = (prefix) => ({
        enabled: form.elements[`${prefix}_enabled`].checked,
        api_key: form.elements[`${prefix}_api_key`].value,
        base_url: form.elements[`${prefix}_base_url`].value,
        model: form.elements[`${prefix}_model`].value,
      });
      const payload = {
        enabled: form.elements.enabled.checked,
        default_provider: form.elements.default_provider.value,
        default_model: form.elements.default_model.value || 'auto',
        provider_order: form.elements.provider_order.value || 'groq,gemini,openrouter',
        timeout_seconds: Number(form.elements.timeout_seconds.value),
        max_retries: Number(form.elements.max_retries.value),
        retry_backoff_seconds: Number(form.elements.retry_backoff_seconds.value),
        ai_router_enabled: form.elements.ai_router_enabled.checked,
        ai_router_prefer_free: form.elements.ai_router_prefer_free.checked,
        ai_router_cooldown_seconds: Number(form.elements.ai_router_cooldown_seconds.value),
        web_search_enabled: form.elements.web_search_enabled.checked,
        web_search_provider: form.elements.web_search_provider.value,
        web_search_max_results: Number(form.elements.web_search_max_results.value),
        web_search_timeout_seconds: Number(form.elements.web_search_timeout_seconds.value),
        web_search_fallback_enabled: form.elements.web_search_fallback_enabled.checked,
        web_search_cache_enabled: form.elements.web_search_cache_enabled.checked,
        web_search_cache_ttl_seconds: Number(form.elements.web_search_cache_ttl_seconds.value),
        web_search_api_key: form.elements.web_search_api_key.value,
        groq: providerPayload('groq'),
        gemini: providerPayload('gemini'),
        openrouter: providerPayload('openrouter'),
      };
      try {
        this.settings = await updateAiSettings(payload);
        ['groq', 'gemini', 'openrouter'].forEach((prefix) => {
          form.elements[`${prefix}_api_key`].value = '';
        });
        this._updateKeyStatuses();
        this._setMessage('Paramètres enregistrés. Les clés saisies sont conservées (masquées).');
      } catch (error) {
        const detail = error.data?.detail;
        const detailText = Array.isArray(detail)
          ? detail.map((item) => item?.msg || JSON.stringify(item)).join(' — ')
          : detail;
        this._setMessage(detailText || error.message || 'Erreur lors de l\'enregistrement.');
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  // ------------------------------------------------------------------ #
  // Rendu
  // ------------------------------------------------------------------ #

  render() {
    this.element = document.createElement('div');
    this.element.className = 'admin-settings-page ai-settings-page';
    this.element.innerHTML = `
      <form data-ai-form>

        <!-- ============ Général ============ -->
        <div class="card">
          <div class="card-header">
            <div>
              <h2>Général</h2>
              <p class="text-muted">Activation globale et fournisseur utilisé par défaut.</p>
            </div>
          </div>
          <div class="card-body">
            <div class="form-row">
              <label class="checkbox-label" data-tooltip="Désactivez pour couper tous les appels IA de l’application.">
                <input name="enabled" type="checkbox"> Passerelle IA activée
              </label>
              <label></label>
            </div>
            <div class="form-row">
              ${this._label('Fournisseur par défaut', 'Choisissez « Automatique » pour laisser le routeur sélectionner le meilleur fournisseur.',
                `<select name="default_provider">
                  <option value="auto">Automatique (selon l’ordre)</option>
                  <option value="groq">Groq</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="openrouter">OpenRouter</option>
                </select>`)}
              ${this._label('Modèle par défaut', 'Nom du modèle (ex : qwen/qwen3.8-27b). « auto » = modèle par défaut du fournisseur.',
                `<input name="default_model" maxlength="100" placeholder="auto">`)}
            </div>
          </div>
        </div>

        <!-- ============ Routage intelligent ============ -->
        <div class="card">
          <div class="card-header">
            <div>
              <h2>Routage intelligent</h2>
              <p class="text-muted">Sélection automatique du meilleur modèle disponible (gratuits en priorité).</p>
            </div>
          </div>
          <div class="card-body">
            <div class="form-row">
              <label class="checkbox-label" data-tooltip="Active la cascade de modèles : le routeur choisit automatiquement le meilleur modèle disponible (OpenCode → Groq → Gemini → OpenRouter).">
                <input name="ai_router_enabled" type="checkbox"> Routage intelligent activé
              </label>
              <label class="checkbox-label" data-tooltip="Privilégie les modèles gratuits (MiMo, Nemotron, etc.) avant les modèles payants.">
                <input name="ai_router_prefer_free" type="checkbox"> Préférer les modèles gratuits
              </label>
            </div>
            <div class="form-row">
              ${this._label('Cooldown par défaut (secondes)', 'Durée d’attente avant de réessayer un modèle après un échec (quota dépassé, timeout, etc.).',
                `<input name="ai_router_cooldown_seconds" type="number" min="0" max="600" step="30" value="300">`)}
              <label></label>
            </div>
        </div>
      </div>

      <!-- ============ Recherche Web ============ -->
      <div class="card">
        <div class="card-header">
          <div>
            <h2>Recherche Web (Agent Sport)</h2>
            <p class="text-muted">Configuration de la recherche Internet autonome pour l’IA Sport (Brave → DuckDuckGo fallback).</p>
          </div>
        </div>
        <div class="card-body">
          <div class="form-row">
            <label class="checkbox-label" data-tooltip="Active la recherche Internet pour l’IA Sport (recommandations nutrition, récupération, trail, etc.).">
              <input name="web_search_enabled" type="checkbox"> Recherche Web activée
            </label>
            <label></label>
          </div>
          <div class="form-row">
            ${this._label('Provider de recherche', 'Provider principal. « brave » nécessite une clé API. « duckduckgo » et « serper » sont des alternatives.',
              `<select name="web_search_provider">
                <option value="brave">Brave Search (recommandé)</option>
                <option value="duckduckgo">DuckDuckGo (gratuit, sans clé)</option>
                <option value="serper">Serper / Google</option>
              </select>`)}
            <label></label>
          </div>
          <div class="form-row">
            ${this._label('Clé API Brave Search', 'Clé API Brave Search. Laisser vide si déjà enregistrée. Obtenir une clé sur api.search.brave.com.',
              `<input name="web_search_api_key" type="password" autocomplete="new-password" placeholder="Non configurée">`)}
            <span class="text-muted" data-key-status="web_search"></span>
          </div>
          <div class="form-row">
            ${this._label('Résultats max', 'Nombre maximum de résultats renvoyés par recherche (1-15).',
              `<input name="web_search_max_results" type="number" min="1" max="15" step="1">`)}
            ${this._label('Timeout (s)', 'Délai maximum avant abandon de la recherche (1-60s).',
              `<input name="web_search_timeout_seconds" type="number" min="1" max="60" step="1">`)}
          </div>
          <div class="form-row">
            <label class="checkbox-label" data-tooltip="Si le provider principal échoue, bascule automatiquement sur DuckDuckGo.">
              <input name="web_search_fallback_enabled" type="checkbox"> Fallback automatique (Brave → DuckDuckGo)
            </label>
            <label></label>
          </div>
          <div class="form-row">
            <label class="checkbox-label" data-tooltip="Mise en cache des résultats pour éviter les requêtes identiques et réduire la latence.">
              <input name="web_search_cache_enabled" type="checkbox"> Cache activé
            </label>
            ${this._label('TTL cache (s)', 'Durée de vie du cache en secondes (min 60s).',
              `<input name="web_search_cache_ttl_seconds" type="number" min="60" max="86400" step="60">`)}
          </div>
        </div>
      </div>

        <!-- ============ Résilience ============ -->
        <div class="card">
          <div class="card-header">
            <div>
              <h2>Résilience et repli</h2>
              <p class="text-muted">Comportement en cas d’erreur : délais, nombre de tentatives et ordre de repli.</p>
            </div>
          </div>
          <div class="card-body">
            <div class="form-row">
              ${this._label('Ordre de repli (fallback)', 'Liste ordonnée de fournisseurs à essayer si le principal échoue (séparés par des virgules).',
                `<input name="provider_order" maxlength="100" placeholder="groq,gemini,openrouter">`)}
              <label></label>
            </div>
            <div class="form-row">
              ${this._label('Timeout (secondes)', 'Délai maximum avant qu’une requête ne soit considérée comme échouée.',
                `<input name="timeout_seconds" type="number" min="1" max="300" step="1">`)}
              ${this._label('Tentatives max', 'Nombre de nouvelles tentatives après un échec avant de passer au fournisseur suivant.',
                `<input name="max_retries" type="number" min="0" max="5" step="1">`)}
            </div>
            <div class="form-row">
              ${this._label('Backoff entre tentatives (secondes)', 'Temps d’attente qui double à chaque nouvelle tentative (1s → 2s → 4s…).',
                `<input name="retry_backoff_seconds" type="number" min="0" max="30" step="0.5">`)}
              <label></label>
            </div>
          </div>
        </div>

        <!-- ============ Fournisseurs ============ -->
        ${this._providerCard('groq', 'Groq', 'Fournisseur rapide et gratuit, idéal pour les appels à haut volume.')}
        ${this._providerCard('gemini', 'Google Gemini', 'Modèles Google (Gemini). Nécessite une clé API Google AI Studio.')}
        ${this._providerCard('openrouter', 'OpenRouter', 'Agrégateur multi-modèles. Un seul accès à des dizaines de fournisseurs.')}

        <!-- ============ Actions ============ -->
        <div class="form-actions ai-form-actions">
          <button class="btn btn-primary" type="submit">Enregistrer</button>
          <span data-ai-message role="status"></span>
        </div>

      </form>
    `;

    this._bindSettingsForm();
    return this.element;
  }

  onTabActivate() {}

  destroy() {}
}

export function createAiSettingsPage() {
  return new AiSettingsPage();
}
