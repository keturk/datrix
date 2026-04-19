import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('PaymentApi Custom Endpoints', () => {
  let app: INestApplication;

  beforeAll(async () => {
    process.env.JWT_SECRET = 'datrix-test-jwt-secret';
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
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/payments/order/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(200);
    });
  });

  describe('GET /api/v1/payments/my-payments', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/payments/my-payments')
        .set('Authorization', 'Bearer test-token')
        .expect(200);
    });
  });

  describe('POST /api/v1/payments/process', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/payments/process')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/payments/00000000-0000-0000-0000-000000000001/refund')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/payments/webhook/stripe', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/payments/webhook/stripe')
        .send({})
        .expect(201);
    });
  });

});
