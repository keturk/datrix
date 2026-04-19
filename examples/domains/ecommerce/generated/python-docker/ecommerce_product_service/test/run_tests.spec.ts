import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../src/app.module';

describe('ProductApi API Tests', () => {
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

  it('GET /api/v1/products/products returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/products/products')
      .expect(200);
  });

  it('GET /api/v1/products/products/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/products/products/00000000-0000-0000-0000-000000000001')
      .expect(200);
  });

  it('POST /api/v1/products/products returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/products/products')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('PUT /api/v1/products/products/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/products/products/00000000-0000-0000-0000-000000000001')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('DELETE /api/v1/products/products/00000000-0000-0000-0000-000000000001 returns 204', async () => {
    const response = await request(app.getHttpServer())
      .delete('/api/v1/products/products/00000000-0000-0000-0000-000000000001')
      .set('Authorization', 'Bearer test-token')
      .expect(204);
  });

  it('GET /api/v1/products/slug/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/products/slug/00000000-0000-0000-0000-000000000001')
      .expect(200);
  });

  it('GET /api/v1/products/search returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/products/search')
      .expect(200);
  });

  it('GET /api/v1/products/category/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/products/category/00000000-0000-0000-0000-000000000001')
      .expect(200);
  });

  it('POST /api/v1/products/ returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/products/')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(201);
  });

  it('PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/products/00000000-0000-0000-0000-000000000001/inventory')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish returns 200', async () => {
    const response = await request(app.getHttpServer())
      .put('/api/v1/products/00000000-0000-0000-0000-000000000001/publish')
      .send({})
      .set('Authorization', 'Bearer test-token')
      .expect(200);
  });

  it('POST /api/v1/products/internal/check-availability returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/products/internal/check-availability')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/products/internal/reserve-inventory returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/products/internal/reserve-inventory')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/products/internal/confirm-reservation returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/products/internal/confirm-reservation')
      .send({})
      .expect(201);
  });

  it('POST /api/v1/products/internal/release-reservation returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/products/internal/release-reservation')
      .send({})
      .expect(201);
  });

  it('GET /api/v1/products/internal/00000000-0000-0000-0000-000000000001 returns 200', async () => {
    const response = await request(app.getHttpServer())
      .get('/api/v1/products/internal/00000000-0000-0000-0000-000000000001')
      .expect(200);
  });

  it('POST /api/v1/products/internal/bulk returns 201', async () => {
    const response = await request(app.getHttpServer())
      .post('/api/v1/products/internal/bulk')
      .send({})
      .expect(201);
  });

});
