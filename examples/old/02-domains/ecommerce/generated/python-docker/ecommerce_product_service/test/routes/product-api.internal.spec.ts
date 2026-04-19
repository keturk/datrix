import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ProductApi Internal Endpoints', () => {
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

  describe('POST /api/v1/products/internal/check-availability (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/check-availability')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/check-availability')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/internal/reserve-inventory (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/reserve-inventory')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/reserve-inventory')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/internal/confirm-reservation (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/confirm-reservation')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/confirm-reservation')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/internal/release-reservation (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/release-reservation')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/release-reservation')
        .expect(403);
    });
  });

  describe('GET /api/v1/products/internal/00000000-0000-0000-0000-000000000001 (internal)', () => {
    it('should handle internal get request', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/products/internal/00000000-0000-0000-0000-000000000001')
        .set('X-Internal-Token', 'internal-service-token')
        .expect(200);
    });

    it('should reject external access to get', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/products/internal/00000000-0000-0000-0000-000000000001')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/internal/bulk (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/bulk')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/internal/bulk')
        .expect(403);
    });
  });

});
