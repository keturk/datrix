/**
 * Deployment verification tests for ecommerce.PaymentService.
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

describe('PaymentApi Deployment Tests', () => {
  it('GET /api/v1/payments/payments/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/payments/payments/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/payments/order/00000000-0000-0000-0000-000000000001`);
    expect(response.status).toBe(200);
  });

  it('GET /api/v1/payments/my-payments returns 200', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/payments/my-payments`);
    expect(response.status).toBe(200);
  });

  it('POST /api/v1/payments/process returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/payments/process`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/payments/00000000-0000-0000-0000-000000000001/refund`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /api/v1/payments/webhook/stripe returns 201', async () => {
    const response = await fetch(`${BASE_URL}/api/v1/payments/webhook/stripe`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

});
