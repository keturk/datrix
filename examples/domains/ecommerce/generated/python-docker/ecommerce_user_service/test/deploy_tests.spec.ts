/**
 * Deployment verification tests for ecommerce.UserService.
 *
 * Run against a live deployed endpoint.
 * Configure BASE_URL via environment variable.
 *
 * Usage: BASE_URL=https://your-service.com npx jest deploy_tests.ts
 */

if (!process.env.BASE_URL) {
  throw new Error('BASE_URL environment variable is required');
}
const BASE_URL = process.env.BASE_URL;

describe('UserApi Deployment Tests', () => {
  it('GET /api/v1/users returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/users`);
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/users/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/users/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/users returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/users`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('PUT /api/v1/users/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/users/00000000-0000-0000-0000-000000000001`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(200);
  });

  it('DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 returns 204', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/users/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(204);
  });

  it('POST /api/v1/register returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/login returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/logout returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/logout`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('GET /api/v1/me returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/me`);
    expect(response.status).toBe(200);
  });

  it('PUT /api/v1/me returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/me`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(200);
  });

  it('PUT /api/v1/me/password returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/me/password`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/verify-email returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/verify-email`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/forgot-password returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/forgot-password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/reset-password returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/reset-password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('PUT /api/v1/00000000-0000-0000-0000-000000000001/status returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/00000000-0000-0000-0000-000000000001/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/internal/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/internal/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/internal/validate-session returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/internal/validate-session`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

});
