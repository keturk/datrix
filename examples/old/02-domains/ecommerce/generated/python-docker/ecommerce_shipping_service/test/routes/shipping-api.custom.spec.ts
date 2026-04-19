import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ShippingApi Custom Endpoints', () => {
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

  describe('GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/shipments/order/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(200);
    });
  });

  describe('GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/shipments/track/00000000-0000-0000-0000-000000000001')
        .expect(200);
    });
  });

  describe('PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status', () => {
    it('should handle put request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/shipments/00000000-0000-0000-0000-000000000001/status')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(200);
    });
  });

  describe('POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/shipments/00000000-0000-0000-0000-000000000001/events')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/shipments/rates', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/shipments/rates')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/shipments/webhook/fedex', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/shipments/webhook/fedex')
        .send({})
        .expect(201);
    });
  });

});
