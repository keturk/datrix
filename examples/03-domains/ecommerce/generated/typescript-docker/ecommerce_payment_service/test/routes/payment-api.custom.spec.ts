import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('PaymentApi Custom Endpoints', () => {
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

  describe('GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/payments/order/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        ;
      expect([200, 404]).toContain(response.status);
    });
  });

  describe('GET /api/v1/payments/my-payments?page=1&perPage=1', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/payments/my-payments?page=1&perPage=1')
        .set('Authorization', 'Bearer test-token')
        ;
      expect(response.status).toBe(200);
    });
  });

  describe('POST /api/v1/payments/process?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/payments/process?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/payments/00000000-0000-0000-0000-000000000001/refund?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect([201, 404]).toContain(response.status);
    });
  });

  describe('POST /api/v1/payments/webhook/stripe?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/payments/webhook/stripe?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

});
