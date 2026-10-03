/**
 * Deployment verification tests for ecommerce.NotificationService.
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

describe('PushDeviceApi Deployment Tests', () => {
  it('POST /push/devices?request=integration-path-value returns 201', async () => {
    const response = await fetch(`${BASE_URL}/push/devices?request=integration-path-value`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

  it('POST /push/devices/unregister?request=integration-path-value returns 201', async () => {
    const response = await fetch(`${BASE_URL}/push/devices/unregister?request=integration-path-value`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    expect(response.status).toBe(201);
  });

});
