import { authStore } from '../stores/auth.js';

export class RegisterPage {
  constructor(router) {
    this.router = router;
    this.element = null;
    this._unsubscribe = null;
  }

  render() {
    this.element = document.createElement('div');
    this.element.className = 'login-page-container';
    this.element.innerHTML = `
      <div class="login-card">
        <header class="login-header">
          <div class="login-header-brand">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
            <h1>ForgeAI</h1>
          </div>
          <p class="subtitle">Créer un compte local</p>
        </header>
        
        <form id="register-form" class="login-form">
          <div id="register-error" class="error-message hidden" role="alert"></div>
          
          <div class="form-group">
            <label for="register-username">Nom d'utilisateur</label>
            <input 
              type="text" 
              id="register-username" 
              name="username" 
              required
              minlength="3"
              maxlength="50"
              autocomplete="username"
              placeholder="Choisissez un identifiant"
              autofocus
            >
          </div>
          
          <div class="form-group">
            <label for="register-email">Email</label>
            <input 
              type="email" 
              id="register-email" 
              name="email" 
              required
              autocomplete="email"
              placeholder="votre@email.com"
            >
          </div>
          
          <div class="form-group">
            <label for="register-firstname">Prénom (optionnel)</label>
            <input 
              type="text" 
              id="register-firstname" 
              name="first_name"
              maxlength="100"
              autocomplete="given-name"
              placeholder="Prénom"
            >
          </div>
          
          <div class="form-group">
            <label for="register-lastname">Nom (optionnel)</label>
            <input 
              type="text" 
              id="register-lastname" 
              name="last_name"
              maxlength="100"
              autocomplete="family-name"
              placeholder="Nom"
            >
          </div>
          
          <div class="form-group">
            <label for="register-password">Mot de passe</label>
            <input 
              type="password" 
              id="register-password" 
              name="password" 
              required
              minlength="8"
              maxlength="128"
              autocomplete="new-password"
              placeholder="Min 8 caractères"
            >
          </div>
          
          <div class="form-group">
            <label for="register-confirm">Confirmer le mot de passe</label>
            <input 
              type="password" 
              id="register-confirm" 
              name="confirm_password" 
              required
              autocomplete="new-password"
              placeholder="Confirmez le mot de passe"
            >
          </div>
          
          <button type="submit" class="btn btn-primary btn-block" id="register-submit">
            <span class="btn-text">Créer mon compte</span>
            <span class="btn-loading hidden">
              <svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle><path d="M12 2a10 10 0 0 1 10 10" stroke-opacity="1"></path></svg>
            </span>
          </button>
        </form>
        
        <div class="login-footer">
          <a href="#" id="show-login-link" class="register-link">Déjà un compte ? Se connecter</a>
        </div>
      </div>
    `;

    this._bindEvents();
    this._subscribeToAuth();
    return this.element;
  }

  _bindEvents() {
    const form = this.element.querySelector('#register-form');
    const submitBtn = this.element.querySelector('#register-submit');
    const loginLink = this.element.querySelector('#show-login-link');
    const passwordInput = this.element.querySelector('#register-password');
    const confirmInput = this.element.querySelector('#register-confirm');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await this._handleRegister();
    });

    loginLink.addEventListener('click', (e) => {
      e.preventDefault();
      this.router.navigate('/login', { replace: true });
    });

    confirmInput.addEventListener('input', () => {
      if (confirmInput.value && passwordInput.value !== confirmInput.value) {
        confirmInput.setCustomValidity('Les mots de passe ne correspondent pas');
      } else {
        confirmInput.setCustomValidity('');
      }
    });

    const inputs = this.element.querySelectorAll('input');
    inputs.forEach(input => {
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
    const submitBtn = this.element?.querySelector('#register-submit');
    const btnText = this.element?.querySelector('.btn-text');
    const btnLoading = this.element?.querySelector('.btn-loading');
    
    if (!submitBtn) return;
    
    submitBtn.disabled = loading;
    if (btnText) btnText.classList.toggle('hidden', loading);
    if (btnLoading) btnLoading.classList.toggle('hidden', !loading);
  }

  async _handleRegister() {
    const formData = new FormData(this.element.querySelector('#register-form'));
    const errorEl = this.element.querySelector('#register-error');

    const password = formData.get('password');
    const confirm = formData.get('confirm_password');

    errorEl.classList.add('hidden');
    errorEl.textContent = '';

    if (password !== confirm) {
      this._showError('Les mots de passe ne correspondent pas');
      return;
    }

    const userData = {
      username: formData.get('username'),
      email: formData.get('email'),
      first_name: formData.get('first_name') || undefined,
      last_name: formData.get('last_name') || undefined,
      password,
    };

    try {
      await authStore.register(userData);
      this.router.navigate('/login', { replace: true });
    } catch (error) {
      const message = error.message || 'Erreur lors de la création du compte';
      this._showError(message);
    }
  }

  _showError(message) {
    const errorEl = this.element.querySelector('#register-error');
    errorEl.textContent = message;
    errorEl.classList.remove('hidden');
  }

  destroy() {
    this._unsubscribe?.();
    this.element = null;
  }
}

export function createRegisterPage(router) {
  return new RegisterPage(router);
}