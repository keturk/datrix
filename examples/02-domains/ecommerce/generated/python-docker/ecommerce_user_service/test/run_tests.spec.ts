import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';

describe('UserApi API Tests', () => {
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

  it('GET /api/v1/users returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/users')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/users/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/users/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('POST /api/v1/users returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/users')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('PUT /api/v1/users/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/users/00000000-0000-0000-0000-000000000001')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 returns 204', async () => {
    const response = await request(app.getHttpServer())
      .delete('/api/v1/users/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(204);
  });

  it('POST /api/v1/register returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/register')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/login returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/login')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/logout returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/logout')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('GET /api/v1/me returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/me')
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('PUT /api/v1/me returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/me')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('PUT /api/v1/me/password returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/me/password')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('POST /api/v1/verify-email returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/verify-email')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/forgot-password returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/forgot-password')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/reset-password returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/reset-password')
      .send({})
      .expect(201);
  });

  it('PUT /api/v1/00000000-0000-0000-0000-000000000001/status returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/00000000-0000-0000-0000-000000000001/status')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('GET /api/v1/internal/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/internal/00000000-0000-0000-0000-000000000001')
      .expect(200);
  });

  it('POST /api/v1/internal/validate-session returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/internal/validate-session')
      .send({})
      .expect(201);
  });

});
