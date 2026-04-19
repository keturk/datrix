import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ProductApi Custom Endpoints', () => {
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

  describe('GET /api/v1/products/slug/00000000-0000-0000-0000-000000000001', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/products/slug/00000000-0000-0000-0000-000000000001')
        .expect(200);
    });
  });

  describe('GET /api/v1/products/search', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/products/search')
        .expect(200);
    });
  });

  describe('GET /api/v1/products/category/00000000-0000-0000-0000-000000000001', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/products/category/00000000-0000-0000-0000-000000000001')
        .expect(200);
    });
  });

  describe('PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory', () => {
    it('should handle put request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/products/00000000-0000-0000-0000-000000000001/inventory')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(200);
    });
  });

  describe('PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish', () => {
    it('should handle put request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/products/00000000-0000-0000-0000-000000000001/publish')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(200);
    });
  });

});
