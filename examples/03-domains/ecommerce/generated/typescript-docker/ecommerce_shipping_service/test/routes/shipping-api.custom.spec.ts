import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ShippingApi Custom Endpoints', () => {
  let app: INestApplication;

  beforeAll(async () => {
    process.env.NODE_ENV = 'test';
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    await app.init();
  });

  afterAll(async () => {
    await app.close();
  });

  describe('GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/shipments/order/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        ;
      expect([200, 404]).toContain(response.status);
    });
  });

  describe('GET /api/v1/shipments/track/test', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/shipments/track/test')
        ;
      expect([200, 404]).toContain(response.status);
    });
  });

  describe('PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/shipments/00000000-0000-0000-0000-000000000001/status?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect([200, 404]).toContain(response.status);
    });
  });

  describe('POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/shipments/00000000-0000-0000-0000-000000000001/events?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect([201, 404]).toContain(response.status);
    });
  });

  describe('POST /api/v1/shipments/rates?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/shipments/rates?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('POST /api/v1/shipments/webhook/fedex?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/shipments/webhook/fedex?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

});
