import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('UserApi Custom Endpoints', () => {
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

  describe('POST /api/v1/register', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/register')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/login', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/login')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/logout', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/logout')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });
  });

  describe('GET /api/v1/me', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/me')
        .set('Authorization', 'Bearer test-token')
        .expect(200);
    });
  });

  describe('PUT /api/v1/me', () => {
    it('should handle put request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/me')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(200);
    });
  });

  describe('PUT /api/v1/me/password', () => {
    it('should handle put request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/me/password')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(200);
    });
  });

  describe('POST /api/v1/verify-email', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/verify-email')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/forgot-password', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/forgot-password')
        .send({})
        .expect(201);
    });
  });

  describe('POST /api/v1/reset-password', () => {
    it('should handle post request', async () => {
      const response = await request(app.getHttpServer())
        .post('/api/v1/reset-password')
        .send({})
        .expect(201);
    });
  });

  describe('PUT /api/v1/00000000-0000-0000-0000-000000000001/status', () => {
    it('should handle put request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/00000000-0000-0000-0000-000000000001/status')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(200);
    });
  });

});
