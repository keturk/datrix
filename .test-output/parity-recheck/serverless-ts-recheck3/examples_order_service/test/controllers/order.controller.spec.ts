import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('OrderController', () => {
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

  describe('GET /api/v1/orders', () => {
    it('should return a list of orders', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/orders')
        .expect(200);

      expect(response.body).toBeInstanceOf(Array);
    });
  });

  describe('GET /api/v1/orders/:id', () => {
    it('should return a single order', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/orders/00000000-0000-0000-0000-000000000001')
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });

    it('should return 404 for non-existent order', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/orders/00000000-0000-0000-0000-000000000099')
        .expect(404);
    });
  });

  describe('PATCH /api/v1/orders/:id', () => {
    it('should update an existing order', async () => {
      const updateDto = {
        amount: 10.5,
        currency: "test_value",
        status: "test_value",
      };

      const response = await request(app.getHttpServer())
        .patch('/api/v1/orders/00000000-0000-0000-0000-000000000001')
        .send(updateDto)
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });
  });

});
