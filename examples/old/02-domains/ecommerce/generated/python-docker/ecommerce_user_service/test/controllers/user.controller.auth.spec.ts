import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('UserController Auth', () => {
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

  describe('GET /api/v1/users (unauthenticated)', () => {
    it('should return 401 without auth token', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/users')
        .expect(401);
    });
  });

  describe('GET /api/v1/users (wrong role)', () => {
    it('should return 403 with wrong role', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/users')
        .set('Authorization', 'Bearer wrong-role-token')
        .expect(403);
    });
  });

  describe('GET /api/v1/users/00000000-0000-0000-0000-000000000001 (unauthenticated)', () => {
    it('should return 401 without auth token', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .expect(401);
    });
  });

  describe('GET /api/v1/users/00000000-0000-0000-0000-000000000001 (wrong role)', () => {
    it('should return 403 with wrong role', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer wrong-role-token')
        .expect(403);
    });
  });

  describe('POST /api/v1/users (unauthenticated)', () => {
    it('should return 401 without auth token', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/users')
        .expect(401);
    });
  });

  describe('POST /api/v1/users (wrong role)', () => {
    it('should return 403 with wrong role', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/users')
        .set('Authorization', 'Bearer wrong-role-token')
        .expect(403);
    });
  });

  describe('PUT /api/v1/users/00000000-0000-0000-0000-000000000001 (unauthenticated)', () => {
    it('should return 401 without auth token', async () => {
      await request(app.getHttpServer())
        .put('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .expect(401);
    });
  });

  describe('PUT /api/v1/users/00000000-0000-0000-0000-000000000001 (wrong role)', () => {
    it('should return 403 with wrong role', async () => {
      await request(app.getHttpServer())
        .put('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer wrong-role-token')
        .expect(403);
    });
  });

  describe('DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 (unauthenticated)', () => {
    it('should return 401 without auth token', async () => {
      await request(app.getHttpServer())
        .delete('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .expect(401);
    });
  });

  describe('DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 (wrong role)', () => {
    it('should return 403 with wrong role', async () => {
      await request(app.getHttpServer())
        .delete('/api/v1/users/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer wrong-role-token')
        .expect(403);
    });
  });

});
