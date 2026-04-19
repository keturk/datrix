import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('OrderApi Internal Endpoints', () => {
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

  describe('GET /api/v1/orders/internal/00000000-0000-0000-0000-000000000001 (internal)', () => {
    it('should handle internal get request', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/orders/internal/00000000-0000-0000-0000-000000000001')
        .set('X-Internal-Token', 'internal-service-token')
        .expect(200);
    });

    it('should reject external access to get', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/orders/internal/00000000-0000-0000-0000-000000000001')
        .expect(403);
    });
  });

  describe('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment')
        .expect(403);
    });
  });

  describe('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment')
        .expect(403);
    });
  });

});
