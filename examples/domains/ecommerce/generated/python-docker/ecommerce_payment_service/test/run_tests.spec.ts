import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';

describe('PaymentApi API Tests', () => {
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

  it('GET /api/v1/payments/payments/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/payments/payments/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/payments/order/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/payments/my-payments returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/payments/my-payments')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('POST /api/v1/payments/process returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/payments/process')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/payments/00000000-0000-0000-0000-000000000001/refund')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('POST /api/v1/payments/webhook/stripe returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/payments/webhook/stripe')
      .send({})
      .expect(201);
  });

});
