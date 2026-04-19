/**
 * Deployment verification tests for ecommerce.OrderService.
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

describe('OrderApi Deployment Tests', () => {
  it('GET /api/v1/orders/ returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/orders/`);
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/orders/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/orders/ returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/orders/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/orders/internal/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/orders/internal/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

});
