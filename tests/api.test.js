const request = require('supertest');
const { app } = require('../src/server/index');
const { todos } = require('../src/server/routes/api');

describe('API Todos', () => {
  beforeEach(() => {
    todos.length = 0;
    todos.push(
      { id: 1, title: 'Tâche 1', completed: true },
      { id: 2, title: 'Tâche 2', completed: false },
      { id: 3, title: 'Tâche 3', completed: false }
    );
  });

  describe('GET /api/todos', () => {
    test('retourne toutes les tâches', async () => {
      const res = await request(app).get('/api/todos');
      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(3);
      expect(res.body[0]).toHaveProperty('id');
      expect(res.body[0]).toHaveProperty('title');
      expect(res.body[0]).toHaveProperty('completed');
    });
  });

  describe('GET /api/todos/:id', () => {
    test('retourne une tâche par son ID', async () => {
      const res = await request(app).get('/api/todos/1');
      expect(res.status).toBe(200);
      expect(res.body.id).toBe(1);
      expect(res.body.title).toBe('Tâche 1');
    });

    test('retourne 404 pour ID inexistant', async () => {
      const res = await request(app).get('/api/todos/999');
      expect(res.status).toBe(404);
      expect(res.body.error).toBe('Todo non trouvé');
    });
  });

  describe('POST /api/todos', () => {
    test('crée une nouvelle tâche', async () => {
      const res = await request(app)
        .post('/api/todos')
        .send({ title: 'Nouvelle tâche' });
      expect(res.status).toBe(201);
      expect(res.body.title).toBe('Nouvelle tâche');
      expect(res.body.completed).toBe(false);
      expect(res.body.id).toBeDefined();
    });

    test('rejette une tâche sans titre', async () => {
      const res = await request(app)
        .post('/api/todos')
        .send({ title: '' });
      expect(res.status).toBe(400);
      expect(res.body.error).toBe('Le titre est requis');
    });

    test('rejette une tâche sans body', async () => {
      const res = await request(app)
        .post('/api/todos')
        .send({});
      expect(res.status).toBe(400);
    });
  });

  describe('PATCH /api/todos/:id', () => {
    test('met à jour le titre', async () => {
      const res = await request(app)
        .patch('/api/todos/1')
        .send({ title: 'Titre modifié' });
      expect(res.status).toBe(200);
      expect(res.body.title).toBe('Titre modifié');
    });

    test('met à jour le statut completed', async () => {
      const res = await request(app)
        .patch('/api/todos/2')
        .send({ completed: true });
      expect(res.status).toBe(200);
      expect(res.body.completed).toBe(true);
    });

    test('met à jour les deux champs', async () => {
      const res = await request(app)
        .patch('/api/todos/3')
        .send({ title: 'Nouveau titre', completed: true });
      expect(res.status).toBe(200);
      expect(res.body.title).toBe('Nouveau titre');
      expect(res.body.completed).toBe(true);
    });

    test('rejette un titre vide', async () => {
      const res = await request(app)
        .patch('/api/todos/1')
        .send({ title: '   ' });
      expect(res.status).toBe(400);
      expect(res.body.error).toBe('Le titre est requis');
    });

    test('retourne 404 pour ID inexistant', async () => {
      const res = await request(app)
        .patch('/api/todos/999')
        .send({ title: 'Test' });
      expect(res.status).toBe(404);
    });
  });

  describe('DELETE /api/todos/:id', () => {
    test('supprime une tâche', async () => {
      const res = await request(app).delete('/api/todos/1');
      expect(res.status).toBe(204);
      
      const getRes = await request(app).get('/api/todos/1');
      expect(getRes.status).toBe(404);
    });

    test('retourne 404 pour ID inexistant', async () => {
      const res = await request(app).delete('/api/todos/999');
      expect(res.status).toBe(404);
    });
  });
});

describe('Health check', () => {
  test('GET /api/todos fonctionne', async () => {
    const res = await request(app).get('/api/todos');
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
  });
});