import { api, ApiError } from '../services/api.js';
import { authStore } from '../stores/auth.js';

export class LoginPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this._unsubscribe = null;
    this._ssoAttempted = false;
    this._initialLoad = true;
  }

  async render() {
    this.element = document.createElement('div');
    this.element.className = 'login-page-container';
    this.element.innerHTML = `
      <div class="login-card">
        <header class="login-header">
          <div class="login-header-brand">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
            <h1>ForgeAI</h1>
          </div>
          <p class="subtitle">Connectez-vous pour accéder à votre espace</p>
        </header>
        
        <div id="sso-status" class="sso-status hidden" role="status" aria-live="polite"></div>

        <form id="login-form" class="login-form">
          <div id="login-error" class="error-message hidden" role="alert"></div>
          
          <div class="form-group">
            <label for="login-username">Nom d'utilisateur</label>
            <input 
              type="text" 
              id="login-username" 
              name="username" 
              required
              autocomplete="username"
              placeholder="Votre identifiant"
              autofocus
            >
          </div>
          
          <div class="form-group">
            <label for="login-password">Mot de passe</label>
            <input 
              type="password" 
              id="login-password" 
              name="password" 
              required
              autocomplete="current-password"
              placeholder="Votre mot de passe"
            >
          </div>
          
          <button type="submit" class="btn btn-primary btn-block" id="login-submit">
            <span class="btn-text">Se connecter</span>
            <span class="btn-loading hidden">
              <svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path d="M12 2a10 10 0 0 1 10 10" stroke-opacity="1"></path></svg>
            </span>
          </button>
        </form>
        
        <div class="login-footer">
        </div>
      </div>
    `;

    this._bindEvents();
    this._subscribeToAuth();
    await this._initialize();
    return this.element;
  }

  async _initialize() {
    // First, check if we already have a valid session
    try {
      await authStore.loadCurrentUser();
      if (authStore.authenticated && authStore.currentUser) {
        // Valid session exists - redirect to dashboard
        this.router.navigate('/dashboard', { replace: true });
        return;
      }
    } catch (error) {
      // No valid session, continue to SSO/login
    }

    // No valid session - attempt SSO if enabled
    await this._trySSOLogin();
  }

  async _trySSOLogin() {
    if (this._ssoAttempted) return;
    this._ssoAttempted = true;

    try {
      const settings = await api.get('/settings');
      if (settings.ad_enabled && settings.ad_sso_enabled) {
        this._showSSOStatus('Connexion automatique en cours...', 'info');
        try {
          await authStore.loginSSO();
          this.router.navigate('/dashboard', { replace: true });
          return;
        } catch (error) {
          // SSO failed - check if we still have a valid session
          try {
            await authStore.loadCurrentUser();
            if (authStore.authenticated && authStore.currentUser) {
              this.router.navigate('/dashboard', { replace: true });
              return;
            }
          } catch (e) {
            // No session, show form
          }
          
          if (error instanceof ApiError && error.status === 401) {
            this._showSSOStatus('Connexion automatique non disponible, utilisez le formulaire ci-dessous.', 'warning');
          } else if (error instanceof ApiError && error.status === 403) {
            this._showSSOStatus('Accès SSO non autorisé, utilisez le formulaire ci-dessous.', 'warning');
          } else {
            this._showSSOStatus('Erreur connexion automatique, utilisez le formulaire ci-dessous.', 'warning');
          }
        }
      }
    } catch (error) {
      console.error('Erreur vérification SSO:', error);
    }
  }

  _showSSOStatus(message, type) {
    const statusEl = this.element?.querySelector('#sso-status');
    if (!statusEl) return;
    statusEl.textContent = message;
    statusEl.className = `sso-status ${type}`;
    statusEl.classList.remove('hidden');
  }

  _bindEvents() {
    const form = this.element.querySelector('#login-form');
    const submitBtn = this.element.querySelector('#login-submit');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this._handleLogin();
    });

    const usernameInput = this.element.querySelector('#login-username');
    const passwordInput = this.element.querySelector('#login-password');
    
    [usernameInput, passwordInput].forEach(input => {
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          form.dispatchEvent(new Event('submit'));
        }
      });
    });
  }

  _subscribeToAuth() {
    this._unsubscribe = authStore.subscribe((state) => {
      this._updateLoadingState(state.loading);
    });
  }

  _updateLoadingState(loading) {
    const submitBtn = this.element?.querySelector('#login-submit');
    const btnText = this.element?.querySelector('.btn-text');
    const btnLoading = this.element?.querySelector('.btn-loading');
    
    if (!submitBtn) return;
    
    submitBtn.disabled = loading;
    if (btnText) btnText.classList.toggle('hidden', loading);
    if (btnLoading) btnLoading.classList.toggle('hidden', !loading);
  }

  async _handleLogin() {
    const usernameInput = this.element.querySelector('#login-username');
    const passwordInput = this.element.querySelector('#login-password');
    const errorEl = this.element.querySelector('#login-error');

    const username = usernameInput.value.trim();
    const password = passwordInput.value;

    errorEl.classList.add('hidden');
    errorEl.textContent = '';

    if (!username || !password) {
      this._showError('Veuillez remplir tous les champs');
      return;
    }

    try {
      await authStore.login(username, password);
      this.router.navigate('/dashboard', { replace: true });
    } catch (error) {
      const message = error.message || 'Identifiants invalides';
      this._showError(message);
      passwordInput.value = '';
      passwordInput.focus();
    }
  }

  _showError(message) {
    const errorEl = this.element.querySelector('#login-error');
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
  }

  destroy() {
    this._unsubscribe?.();
    this.element = null;
  }
}

export function createLoginPage(router) {
  return new LoginPage(router);
}