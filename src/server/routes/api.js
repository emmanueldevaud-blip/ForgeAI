const express = require('express');

const router = express.Router();

let todos = [
  { id: 1, title: 'Apprendre Node.js', completed: true },
  { id: 2, title: 'Créer une API REST', completed: false },
  { id: 3, title: 'Écrire des tests', completed: false }
];
let nextId = 4;

function validateTodo(req, res, next) {
  const { title } = req.body;
  if (!title || typeof title !== 'string' || title.trim() === '') {
    return res.status(400).json({ error: 'Le titre est requis' });
  }
  next();
}

router.get('/todos', (req, res) => {
  res.json(todos);
});

router.get('/todos/:id', (req, res) => {
  const id = parseInt(req.params.id);
  const todo = todos.find(t => t.id === id);
  if (!todo) {
    return res.status(404).json({ error: 'Todo non trouvé' });
  }
  res.json(todo);
});

router.post('/todos', validateTodo, (req, res) => {
  const todo = {
    id: nextId++,
    title: req.body.title.trim(),
    completed: false
  };
  todos.push(todo);
  res.status(201).json(todo);
});

router.patch('/todos/:id', (req, res) => {
  const id = parseInt(req.params.id);
  const todo = todos.find(t => t.id === id);
  if (!todo) {
    return res.status(404).json({ error: 'Todo non trouvé' });
  }
  if (req.body.title !== undefined) {
    if (!req.body.title || typeof req.body.title !== 'string' || req.body.title.trim() === '') {
      return res.status(400).json({ error: 'Le titre est requis' });
    }
    todo.title = req.body.title.trim();
  }
  if (req.body.completed !== undefined) {
    todo.completed = Boolean(req.body.completed);
  }
  res.json(todo);
});

router.delete('/todos/:id', (req, res) => {
  const id = parseInt(req.params.id);
  const index = todos.findIndex(t => t.id === id);
  if (index === -1) {
    return res.status(404).json({ error: 'Todo non trouvé' });
  }
  todos.splice(index, 1);
  res.status(204).send();
});

module.exports = { router, todos };