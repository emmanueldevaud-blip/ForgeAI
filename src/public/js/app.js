const API_BASE = '/auth';
const TODO_API_BASE = '/api';

let currentFilter = 'all';
let todos = [];
let currentUser = null;

const pages = {
  login: document.getElementById('login-page'),
  register: document.getElementById('register-page'),
  main: document.getElementById('main-page'),
};

const elements = {
  loginForm: document.getElementById('login-form'),
  registerForm: document.getElementById('register-form'),
  loginError: document.getElementById('login-error'),
  registerError: document.getElementById('register-error'),
  showRegister: document.getElementById('show-register'),
  showLogin: document.getElementById('show-login'),
  logoutBtn: document.getElementById('logout-btn'),
  userDisplay: document.getElementById('user-display'),
  userRoleBadge: document.getElementById('user-role-badge'),
  adminPanel: document.getElementById('admin-panel'),
  manageUsersBtn: document.getElementById('manage-users-btn'),
  manageAdBtn: document.getElementById('manage-ad-btn'),
  todoForm: document.getElementById('todo-form'),
  todoInput: document.getElementById('todo-input'),
  todoList: document.getElementById('todo-list'),
  filterBtns: document.querySelectorAll('.filter-btn'),
  totalCount: document.getElementById('total-count'),
  activeCount: document.getElementById('active-count'),
  completedCount: document.getElementById('completed-count'),
  userModal: document.getElementById('user-modal'),
  modalClose: document.querySelector('.modal-close'),
  modalOverlay: document.querySelector('.modal-overlay'),
  createUserForm: document.getElementById('create-user-form'),
  modalError: document.getElementById('modal-error'),
  modalSuccess: document.getElementById('modal-success'),
  usersTableBody: document.getElementById('users-table-body'),
  usersList: document.getElementById('users-list'),
  adConfigPanel: document.getElementById('ad-config-panel'),
  adConfigForm: document.getElementById('ad-config-form'),
  adConfigError: document.getElementById('ad-config-error'),
  adConfigSuccess: document.getElementById('ad-config-success'),
  adEnabled: document.getElementById('ad-enabled'),
  adTestBtn: document.getElementById('ad-test-btn'),
  adTestResult: document.getElementById('ad-test-result'),
  adNotice: document.getElementById('ad-notice'),
  registerLink: document.getElementById('register-link'),
};

async function apiRequest(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(error.detail || `Erreur ${response.status}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function todoApiRequest(endpoint, options = {}) {
  const response = await fetch(`${TODO_API_BASE}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
    throw new Error(error.detail || `Erreur ${response.status}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

function showPage(pageName) {
  Object.values(pages).forEach(p => p.classList.add('hidden'));
  pages[pageName].classList.remove('hidden');
}

function showError(element, message) {
  element.textContent = message;
  element.classList.remove('hidden');
}

function hideError(element) {
  element.classList.add('hidden');
}

function showModalError(message) {
  elements.modalError.textContent = message;
  elements.modalError.classList.remove('hidden');
  elements.modalSuccess.classList.add('hidden');
}

function showModalSuccess(message) {
  elements.modalSuccess.textContent = message;
  elements.modalSuccess.classList.remove('hidden');
  elements.modalError.classList.add('hidden');
}

function hideModalMessages() {
  elements.modalError.classList.add('hidden');
  elements.modalSuccess.classList.add('hidden');
}

async function checkAuth() {
  try {
    const user = await apiRequest('/me');
    currentUser = user;
    return true;
  } catch {
    currentUser = null;
    return false;
  }
}

async function login(username, password) {
  hideError(elements.loginError);
  try {
    const response = await apiRequest('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    currentUser = response.user;
    return true;
  } catch (error) {
    showError(elements.loginError, error.message);
    return false;
  }
}

async function register(userData) {
  hideError(elements.registerError);
  try {
    await apiRequest('/register', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
    return true;
  } catch (error) {
    showError(elements.registerError, error.message);
    return false;
  }
}

async function logout() {
  try {
    await apiRequest('/logout', { method: 'POST' });
  } catch {
    // Ignore logout errors
  }
  currentUser = null;
  todos = [];
  showPage('login');
}

async function loadTodos() {
  try {
    todos = await todoApiRequest('/todos');
    renderTodos();
  } catch (error) {
    console.error('Erreur chargement:', error);
    showToast('Impossible de charger les tâches');
  }
}

async function addTodo(title) {
  try {
    const todo = await todoApiRequest('/todos', {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
    todos.unshift(todo);
    renderTodos();
    elements.todoInput.value = '';
  } catch (error) {
    console.error('Erreur ajout:', error);
    showToast(error.message);
  }
}

async function toggleTodo(id, completed) {
  try {
    const updated = await todoApiRequest(`/todos/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ completed }),
    });
    const index = todos.findIndex(t => t.id === id);
    if (index !== -1) todos[index] = updated;
    renderTodos();
  } catch (error) {
    console.error('Erreur mise à jour:', error);
    showToast(error.message);
    loadTodos();
  }
}

async function updateTodoTitle(id, title) {
  try {
    const updated = await todoApiRequest(`/todos/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
    const index = todos.findIndex(t => t.id === id);
    if (index !== -1) todos[index] = updated;
    renderTodos();
  } catch (error) {
    console.error('Erreur mise à jour titre:', error);
    showToast(error.message);
    loadTodos();
  }
}

async function deleteTodo(id) {
  try {
    await todoApiRequest(`/todos/${id}`, { method: 'DELETE' });
    todos = todos.filter(t => t.id !== id);
    renderTodos();
  } catch (error) {
    console.error('Erreur suppression:', error);
    showToast(error.message);
  }
}

function getFilteredTodos() {
  switch (currentFilter) {
    case 'active':
      return todos.filter(t => !t.completed);
    case 'completed':
      return todos.filter(t => t.completed);
    default:
      return todos;
  }
}

function renderTodos() {
  const filtered = getFilteredTodos();

  if (filtered.length === 0) {
    elements.todoList.innerHTML = `
      <li class="empty-state">
        <p>${getEmptyMessage()}</p>
      </li>
    `;
  } else {
    elements.todoList.innerHTML = filtered.map(todo => `
      <li class="todo-item ${todo.completed ? 'completed' : ''}" data-id="${todo.id}">
        <input 
          type="checkbox" 
          class="todo-checkbox" 
          ${todo.completed ? 'checked' : ''}
          aria-label="Marquer comme ${todo.completed ? 'non terminée' : 'terminée'}"
        >
        <span class="todo-title" contenteditable="true" data-original="${escapeHtml(todo.title)}">${escapeHtml(todo.title)}</span>
        <button class="todo-delete" aria-label="Supprimer">🗑️</button>
      </li>
    `).join('');
  }

  updateStats();
  attachTodoEventListeners();
}

function getEmptyMessage() {
  switch (currentFilter) {
    case 'active':
      return 'Aucune tâche active 🎉';
    case 'completed':
      return 'Aucune tâche terminée';
    default:
      return 'Aucune tâche pour le moment. Ajoutez-en une !';
  }
}

function updateStats() {
  const total = todos.length;
  const completed = todos.filter(t => t.completed).length;
  const active = total - completed;

  elements.totalCount.textContent = total;
  elements.activeCount.textContent = active;
  elements.completedCount.textContent = completed;
}

function attachTodoEventListeners() {
  document.querySelectorAll('.todo-checkbox').forEach(checkbox => {
    checkbox.addEventListener('change', (e) => {
      const id = parseInt(e.target.closest('.todo-item').dataset.id);
      toggleTodo(id, e.target.checked);
    });
  });

  document.querySelectorAll('.todo-delete').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const id = parseInt(e.target.closest('.todo-item').dataset.id);
      if (confirm('Supprimer cette tâche ?')) {
        deleteTodo(id);
      }
    });
  });

  document.querySelectorAll('.todo-title').forEach(span => {
    let originalTitle = span.dataset.original;

    span.addEventListener('blur', (e) => {
      const newTitle = e.target.textContent.trim();
      const id = parseInt(e.target.closest('.todo-item').dataset.id);
      if (newTitle && newTitle !== originalTitle) {
        updateTodoTitle(id, newTitle);
      } else {
        e.target.textContent = originalTitle;
      }
    });

    span.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        e.target.blur();
      }
      if (e.key === 'Escape') {
        e.target.textContent = originalTitle;
        e.target.blur();
      }
    });
  });
}

function updateUserUI() {
  if (!currentUser) return;
  elements.userDisplay.textContent = currentUser.full_name || currentUser.username;
  if (currentUser.is_admin || currentUser.role === 'admin') {
    elements.userRoleBadge.textContent = 'Admin';
    elements.userRoleBadge.classList.add('admin');
    elements.userRoleBadge.classList.remove('hidden');
    elements.adminPanel.classList.remove('hidden');
  } else {
    elements.userRoleBadge.classList.add('hidden');
    elements.adminPanel.classList.add('hidden');
  }
}

function openUserModal() {
  elements.userModal.classList.remove('hidden');
  hideModalMessages();
  loadUsersForModal();
}

function closeUserModal() {
  elements.userModal.classList.add('hidden');
  elements.createUserForm.reset();
}

function showAdConfigError(message) {
  elements.adConfigError.textContent = message;
  elements.adConfigError.classList.remove('hidden');
  elements.adConfigSuccess.classList.add('hidden');
}

function showAdConfigSuccess(message) {
  elements.adConfigSuccess.textContent = message;
  elements.adConfigSuccess.classList.remove('hidden');
  elements.adConfigError.classList.add('hidden');
}

function hideAdConfigMessages() {
  elements.adConfigError.classList.add('hidden');
  elements.adConfigSuccess.classList.add('hidden');
}

function showAdTestResult(success, message, details) {
  elements.adTestResult.classList.remove('hidden');
  elements.adTestResult.innerHTML = `
    <div class="ad-test-result ${success ? 'success' : 'error'}">
      <strong>${success ? '✓ Succès' : '✗ Échec'} :</strong> ${message}
      ${details ? `<pre>${escapeHtml(details)}</pre>` : ''}
    </div>
  `;
}

function hideAdTestResult() {
  elements.adTestResult.classList.add('hidden');
}

async function loadAdSettings() {
  try {
    const settings = await apiRequest('/ad-settings');
    populateAdForm(settings);
  } catch (error) {
    console.error('Erreur chargement config AD:', error);
    showAdConfigError('Impossible de charger la configuration AD');
  }
}

function populateAdForm(settings) {
  elements.adEnabled.checked = settings.ad_enabled;
  document.getElementById('ad-server').value = settings.ad_server || '';
  document.getElementById('ad-port').value = settings.ad_port || 636;
  document.getElementById('ad-use-ssl').checked = settings.ad_use_ssl !== false;
  document.getElementById('ad-base-dn').value = settings.ad_base_dn || '';
  document.getElementById('ad-user-dn').value = settings.ad_user_dn || '';
  document.getElementById('ad-user-search-filter').value = settings.ad_user_search_filter || '(sAMAccountName={username})';
  document.getElementById('ad-group-search-base').value = settings.ad_group_search_base || '';
  document.getElementById('ad-admin-group').value = settings.ad_admin_group || '';
  document.getElementById('ad-bind-user').value = settings.ad_bind_user || '';
  document.getElementById('ad-bind-password').value = '';
  document.getElementById('ad-connect-timeout').value = settings.ad_connect_timeout || 10;
  document.getElementById('ad-receive-timeout').value = settings.ad_receive_timeout || 10;
}

function getAdFormData() {
  const formData = new FormData(elements.adConfigForm);
  const data = {};
  for (const [key, value] of formData.entries()) {
    if (key === 'ad_enabled') {
      data[key] = elements.adEnabled.checked;
    } else if (key === 'ad_port' || key === 'ad_connect_timeout' || key === 'ad_receive_timeout') {
      data[key] = parseInt(value, 10);
    } else if (key === 'ad_use_ssl') {
      data[key] = document.getElementById('ad-use-ssl').checked;
    } else if (key === 'ad_bind_password' && value === '') {
      continue;
    } else {
      data[key] = value;
    }
  }
  return data;
}

async function saveAdSettings() {
  hideAdConfigMessages();
  hideAdTestResult();

  const data = getAdFormData();

  try {
    await apiRequest('/ad-settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    showAdConfigSuccess('Configuration AD enregistrée avec succès');
    await loadAdSettings();
  } catch (error) {
    showAdConfigError(error.message);
  }
}

async function testAdConnection() {
  hideAdTestResult();

  const formData = new FormData(elements.adConfigForm);
  const testData = {
    ad_server: formData.get('ad_server') || document.getElementById('ad-server').value,
    ad_port: parseInt(formData.get('ad_port') || document.getElementById('ad-port').value, 10),
    ad_use_ssl: document.getElementById('ad-use-ssl').checked,
    ad_base_dn: formData.get('ad_base_dn') || document.getElementById('ad-base-dn').value,
    ad_bind_user: formData.get('ad_bind_user') || document.getElementById('ad-bind-user').value,
    ad_bind_password: formData.get('ad_bind_password') || document.getElementById('ad-bind-password').value,
    ad_connect_timeout: parseInt(formData.get('ad_connect_timeout') || document.getElementById('ad-connect-timeout').value, 10),
    ad_receive_timeout: parseInt(formData.get('ad_receive_timeout') || document.getElementById('ad-receive-timeout').value, 10),
  };

  if (!testData.ad_server || !testData.ad_base_dn || !testData.ad_bind_user || !testData.ad_bind_password) {
    showAdTestResult(false, 'Veuillez remplir tous les champs obligatoires (serveur, base DN, bind user, mot de passe)');
    return;
  }

  elements.adTestBtn.disabled = true;
  elements.adTestBtn.textContent = 'Test en cours...';

  try {
    const result = await apiRequest('/ad-test', {
      method: 'POST',
      body: JSON.stringify(testData),
    });
    showAdTestResult(result.success, result.message, result.details);
  } catch (error) {
    showAdTestResult(false, error.message);
  } finally {
    elements.adTestBtn.disabled = false;
    elements.adTestBtn.textContent = 'Tester la connexion';
  }
}

function showAdConfigPanel() {
  elements.usersList.classList.add('hidden');
  elements.adConfigPanel.classList.remove('hidden');
  elements.createUserForm.closest('.modal-form').style.display = 'none';
  document.querySelector('.modal-divider').style.display = 'none';
  loadAdSettings();
}

function showUsersList() {
  elements.usersList.classList.remove('hidden');
  elements.adConfigPanel.classList.add('hidden');
  elements.createUserForm.closest('.modal-form').style.display = 'block';
  document.querySelector('.modal-divider').style.display = 'block';
  loadUsersForModal();
}

async function loadUsersForModal() {
  try {
    const users = await apiRequest('/users');
    renderUsersTable(users);
  } catch (error) {
    console.error('Erreur chargement utilisateurs:', error);
    showModalError('Impossible de charger les utilisateurs');
  }
}

function renderUsersTable(users) {
  elements.usersTableBody.innerHTML = users.map(user => `
    <tr>
      <td>
        <div class="user-info">
          <span class="username">${escapeHtml(user.username)}</span>
          <span class="fullname">${escapeHtml(user.full_name || '')}</span>
        </div>
      </td>
      <td>${escapeHtml(user.email)}</td>
      <td>
        <span class="role-badge small ${user.role}">${user.role === 'admin' ? 'Admin' : 'User'}</span>
      </td>
      <td>
        <span class="status-badge ${user.is_active ? 'active' : 'inactive'}">
          ${user.is_active ? 'Actif' : 'Inactif'}
        </span>
      </td>
      <td><span class="source-badge">${user.source}</span></td>
      <td>
        <div class="action-buttons">
          ${user.source === 'local' ? `
            <button class="action-btn reset-password" data-user-id="${user.id}" title="Réinitialiser mot de passe">🔑</button>
            <button class="action-btn toggle-active" data-user-id="${user.id}" data-active="${user.is_active}" title="${user.is_active ? 'Désactiver' : 'Activer'}">${user.is_active ? '🔒' : '🔓'}</button>
            <button class="action-btn delete" data-user-id="${user.id}" title="Supprimer">🗑️</button>
          ` : '<span style="color:#999">AD</span>'}
        </div>
      </td>
    </tr>
  `).join('');

  attachUserActionListeners();
}

function attachUserActionListeners() {
  document.querySelectorAll('.action-btn.reset-password').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const userId = parseInt(e.target.dataset.userId);
      const newPassword = prompt('Nouveau mot de passe (min 8 caractères):');
      if (!newPassword || newPassword.length < 8) {
        showToast('Mot de passe trop court');
        return;
      }
      try {
        await apiRequest(`/users/${userId}/reset-password`, {
          method: 'POST',
          body: JSON.stringify({ new_password: newPassword }),
        });
        showModalSuccess('Mot de passe réinitialisé');
      } catch (error) {
        showModalError(error.message);
      }
    });
  });

  document.querySelectorAll('.action-btn.toggle-active').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const userId = parseInt(e.target.dataset.userId);
      const isActive = e.target.dataset.active === 'true';
      try {
        await apiRequest(`/users/${userId}`, {
          method: 'PATCH',
          body: JSON.stringify({ is_active: !isActive }),
        });
        showModalSuccess(isActive ? 'Utilisateur désactivé' : 'Utilisateur activé');
        loadUsersForModal();
      } catch (error) {
        showModalError(error.message);
      }
    });
  });

  document.querySelectorAll('.action-btn.delete').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const userId = parseInt(e.target.dataset.userId);
      if (confirm('Supprimer cet utilisateur ?')) {
        try {
          await apiRequest(`/users/${userId}`, { method: 'DELETE' });
          showModalSuccess('Utilisateur supprimé');
          loadUsersForModal();
        } catch (error) {
          showModalError(error.message);
        }
      }
    });
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showToast(message) {
  const toast = document.createElement('div');
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%);
    background: #e74c3c; color: white; padding: 1rem 2rem;
    border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    z-index: 1000; animation: slideUp 0.3s ease;
  `;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideUp 0.3s ease reverse';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function showSuccessToast(message) {
  const toast = document.createElement('div');
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%);
    background: #16a34a; color: white; padding: 1rem 2rem;
    border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    z-index: 1000; animation: slideUp 0.3s ease;
  `;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'slideUp 0.3s ease reverse';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

elements.loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const username = formData.get('username');
  const password = formData.get('password');
  if (await login(username, password)) {
    showPage('main');
    updateUserUI();
    await loadTodos();
  }
});

elements.registerForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const password = formData.get('password');
  const confirm = formData.get('confirm_password');
  if (password !== confirm) {
    showError(elements.registerError, 'Les mots de passe ne correspondent pas');
    return;
  }
  const userData = {
    username: formData.get('username'),
    email: formData.get('email'),
    first_name: formData.get('first_name') || undefined,
    last_name: formData.get('last_name') || undefined,
    password,
  };
  if (await register(userData)) {
    showSuccessToast('Compte créé ! Vous pouvez maintenant vous connecter.');
    showPage('login');
    elements.registerForm.reset();
  }
});

elements.logoutBtn.addEventListener('click', logout);

elements.showRegister.addEventListener('click', (e) => {
  e.preventDefault();
  showPage('register');
  hideError(elements.loginError);
});

elements.showLogin.addEventListener('click', (e) => {
  e.preventDefault();
  showPage('login');
  hideError(elements.registerError);
});

elements.manageUsersBtn.addEventListener('click', () => {
  showUsersList();
  openUserModal();
});

elements.manageAdBtn.addEventListener('click', () => {
  showAdConfigPanel();
  openUserModal();
});

elements.modalClose.addEventListener('click', closeUserModal);
elements.modalOverlay.addEventListener('click', closeUserModal);

elements.adConfigForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  await saveAdSettings();
});

elements.adTestBtn.addEventListener('click', testAdConnection);

elements.createUserForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideModalMessages();
  const formData = new FormData(e.target);
  const userData = {
    username: formData.get('username'),
    email: formData.get('email'),
    first_name: formData.get('first_name') || undefined,
    last_name: formData.get('last_name') || undefined,
    password: formData.get('password'),
    role: formData.get('role'),
    is_active: formData.get('is_active') === 'on',
  };
  try {
    await apiRequest('/users', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
    showModalSuccess('Utilisateur créé');
    elements.createUserForm.reset();
    loadUsersForModal();
  } catch (error) {
    showModalError(error.message);
  }
});

elements.filterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    elements.filterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    renderTodos();
  });
});

elements.todoForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const title = elements.todoInput.value.trim();
  if (title) addTodo(title);
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !elements.userModal.classList.contains('hidden')) {
    closeUserModal();
  }
});

document.addEventListener('DOMContentLoaded', async () => {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideUp {
      from { opacity: 0; transform: translateX(-50%) translateY(20px); }
      to { opacity: 1; transform: translateX(-50%) translateY(0); }
    }
  `;
  document.head.appendChild(style);

  const authenticated = await checkAuth();
  if (authenticated) {
    showPage('main');
    updateUserUI();
    await loadTodos();
  } else {
    showPage('login');
    try {
      const settings = await fetch('/auth/settings').then(r => r.json());
      if (settings.ad_enabled) {
        elements.adNotice.classList.remove('hidden');
      }
      if (settings.auth_local_enabled) {
        elements.registerLink.classList.remove('hidden');
      }
    } catch {
      // Ignore
    }
  }
});