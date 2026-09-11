import { api, ApiError } from '../services/api.js';

class AuthStore {
  constructor() {
    this.currentUser = null;
    this.authenticated = false;
    this.loading = false;
    this.permissions = new Set();
    this.roles = [];
    this._listeners = new Set();
    this._loadPromise = null;
  }

  subscribe(listener) {
    this._listeners.add(listener);
    return () => this._listeners.delete(listener);
  }

  _notify() {
    this._listeners.forEach(listener => listener(this.getState()));
  }

  getState() {
    return {
      currentUser: this.currentUser,
      authenticated: this.authenticated,
      loading: this.loading,
      permissions: Array.from(this.permissions),
      roles: this.roles,
    };
  }

  hasPermission(permission) {
    if (this.permissions.has('*')) return true;
    return this.permissions.has(permission);
  }

  hasAnyPermission(permissions) {
    if (this.permissions.has('*')) return true;
    return permissions.some(p => this.permissions.has(p));
  }

  hasAllPermissions(permissions) {
    if (this.permissions.has('*')) return true;
    return permissions.every(p => this.permissions.has(p));
  }

  hasRole(role) {
    return this.roles.includes(role);
  }

  async loadCurrentUser() {
    if (this._loadPromise) {
      return this._loadPromise;
    }

    this.loading = true;
    this._notify();

    this._loadPromise = (async () => {
      try {
        const user = await api.get('/me');
        this.currentUser = user;
        this.authenticated = true;
        this.roles = user.roles || [];
        if (user.permissions) {
          this.permissions = new Set(user.permissions);
        }
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          this.clear();
        } else {
          console.error('Erreur chargement utilisateur:', error);
        }
      } finally {
        this.loading = false;
        this._loadPromise = null;
        this._notify();
      }
    })();

    return this._loadPromise;
  }

  async login(username, password) {
    this.loading = true;
    this._notify();

    try {
      const response = await api.post('/login', { username, password });
      this.currentUser = response.user;
      this.authenticated = true;
      this.roles = response.user.roles || [];
      if (response.user.permissions) {
        this.permissions = new Set(response.user.permissions);
      }
      this._notify();
      return true;
    } catch (error) {
      this.loading = false;
      this._notify();
      throw error;
    }
  }

  async register(userData) {
    this.loading = true;
    this._notify();

    try {
      await api.post('/register', userData);
      this.loading = false;
      this._notify();
      return true;
    } catch (error) {
      this.loading = false;
      this._notify();
      throw error;
    }
  }

  async logout() {
    try {
      await api.post('/logout');
    } catch (error) {
      console.error('Erreur déconnexion:', error);
    } finally {
      this.clear();
    }
  }

  clear() {
    this.currentUser = null;
    this.authenticated = false;
    this.loading = false;
    this.permissions.clear();
    this.roles = [];
    this._notify();
  }

  refresh() {
    return this.loadCurrentUser();
  }

  getUserDisplayName() {
    if (!this.currentUser) return '';
    return this.currentUser.full_name || this.currentUser.username;
  }

  isAdmin() {
    return this.hasRole('admin') || this.hasPermission('admin.access');
  }
}

const authStore = new AuthStore();
export { AuthStore, authStore };