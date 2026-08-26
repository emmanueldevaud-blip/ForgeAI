const API_BASE = '/api';

let currentFilter = 'all';
let todos = [];

const elements = {
  form: document.getElementById('todo-form'),
  input: document.getElementById('todo-input'),
  list: document.getElementById('todo-list'),
  filterBtns: document.querySelectorAll('.filter-btn'),
  totalCount: document.getElementById('total-count'),
  activeCount: document.getElementById('active-count'),
  completedCount: document.getElementById('completed-count')
};

async function apiRequest(endpoint, options = {}) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Erreur inconnue' }));
    throw new Error(error.error || `Erreur ${response.status}`);
  }
  
  if (response.status === 204) return null;
  return response.json();
}

async function loadTodos() {
  try {
    todos = await apiRequest('/todos');
    render();
  } catch (error) {
    console.error('Erreur chargement:', error);
    showError('Impossible de charger les tâches');
  }
}

async function addTodo(title) {
  try {
    const todo = await apiRequest('/todos', {
      method: 'POST',
      body: JSON.stringify({ title })
    });
    todos.unshift(todo);
    render();
    elements.input.value = '';
  } catch (error) {
    console.error('Erreur ajout:', error);
    showError(error.message);
  }
}

async function toggleTodo(id, completed) {
  try {
    const updated = await apiRequest(`/todos/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ completed })
    });
    const index = todos.findIndex(t => t.id === id);
    if (index !== -1) todos[index] = updated;
    render();
  } catch (error) {
    console.error('Erreur mise à jour:', error);
    showError(error.message);
    loadTodos();
  }
}

async function updateTodoTitle(id, title) {
  try {
    const updated = await apiRequest(`/todos/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title })
    });
    const index = todos.findIndex(t => t.id === id);
    if (index !== -1) todos[index] = updated;
    render();
  } catch (error) {
    console.error('Erreur mise à jour titre:', error);
    showError(error.message);
    loadTodos();
  }
}

async function deleteTodo(id) {
  try {
    await apiRequest(`/todos/${id}`, { method: 'DELETE' });
    todos = todos.filter(t => t.id !== id);
    render();
  } catch (error) {
    console.error('Erreur suppression:', error);
    showError(error.message);
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

function render() {
  const filtered = getFilteredTodos();
  
  if (filtered.length === 0) {
    elements.list.innerHTML = `
      <li class="empty-state">
        <p>${getEmptyMessage()}</p>
      </li>
    `;
  } else {
    elements.list.innerHTML = filtered.map(todo => `
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
  attachEventListeners();
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

function attachEventListeners() {
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

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function showError(message) {
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

elements.form.addEventListener('submit', (e) => {
  e.preventDefault();
  const title = elements.input.value.trim();
  if (title) addTodo(title);
});

elements.filterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    elements.filterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    render();
  });
});

document.addEventListener('DOMContentLoaded', loadTodos);

const style = document.createElement('style');
style.textContent = `
  @keyframes slideUp {
    from { opacity: 0; transform: translateX(-50%) translateY(20px); }
    to { opacity: 1; transform: translateX(-50%) translateY(0); }
  }
`;
document.head.appendChild(style);