import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('UserApi Custom Endpoints', () => {
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

  describe('POST /api/v1/register?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/register?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('POST /api/v1/login?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/login?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('POST /api/v1/logout?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/logout?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('GET /api/v1/me', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/me')
        .set('Authorization', 'Bearer test-token')
        ;
      expect(response.status).toBe(200);
    });
  });

  describe('PUT /api/v1/me?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/me?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect(response.status).toBe(200);
    });
  });

  describe('PUT /api/v1/me/password?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/me/password?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect(response.status).toBe(200);
    });
  });

  describe('POST /api/v1/verify-email?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/verify-email?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('POST /api/v1/forgot-password?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/forgot-password?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('POST /api/v1/reset-password?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/reset-password?request=integration-path-value')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('PUT /api/v1/00000000-0000-0000-0000-000000000001/status?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/00000000-0000-0000-0000-000000000001/status?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect([200, 404]).toContain(response.status);
    });
  });

});
