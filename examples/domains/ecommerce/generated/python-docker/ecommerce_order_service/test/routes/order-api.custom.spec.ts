import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('OrderApi Custom Endpoints', () => {
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

  describe('GET /api/v1/orders/', () => {
    it('should handle get request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/orders/')
        .set('Authorization', 'Bearer test-token')
        .expect(200);
    });
  });

  describe('PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel', () => {
    it('should handle put request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(200);
    });
  });

});
