import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';

describe('OrderApi API Tests', () => {
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

  it('GET /api/v1/orders/ returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/orders/')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/orders/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/orders/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('POST /api/v1/orders/ returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/orders/')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/orders/internal/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/orders/internal/00000000-0000-0000-0000-000000000001')
      .expect(200);
  });

  it('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment')
      .send({})
      .expect(201);
  });

});
