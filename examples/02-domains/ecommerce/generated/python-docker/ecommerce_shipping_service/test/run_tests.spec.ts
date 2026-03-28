import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';

describe('ShippingApi API Tests', () => {
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

  it('GET /api/v1/shipments/shipments/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/shipments/shipments/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/shipments/order/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/shipments/track/00000000-0000-0000-0000-000000000001')
      .expect(200);
  });

  it('POST /api/v1/shipments/ returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/shipments/')
      .send({})
      .expect(201);
  });

  it('PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/shipments/00000000-0000-0000-0000-000000000001/status')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/shipments/00000000-0000-0000-0000-000000000001/events')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('POST /api/v1/shipments/rates returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/shipments/rates')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/shipments/webhook/fedex returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/shipments/webhook/fedex')
      .send({})
      .expect(201);
  });

});
