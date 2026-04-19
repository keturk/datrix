/**
 * Deployment verification tests for ecommerce.ShippingService.
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

describe('ShippingApi Deployment Tests', () => {
  it('GET /api/v1/shipments/shipments/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/shipments/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/order/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/track/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/shipments/ returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/00000000-0000-0000-0000-000000000001/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/00000000-0000-0000-0000-000000000001/events`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/shipments/rates returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/rates`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/shipments/webhook/fedex returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/shipments/webhook/fedex`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

});
