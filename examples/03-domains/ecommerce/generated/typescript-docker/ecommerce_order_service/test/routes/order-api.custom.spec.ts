import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('OrderApi Custom Endpoints', () => {
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

  describe('GET /api/v1/orders/?page=1&perPage=1&status=pending', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/orders/?page=1&perPage=1&status=pending')
        .set('Authorization', 'Bearer test-token')
        ;
      expect(response.status).toBe(200);
    });
  });

  describe('PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel?request=integration-path-value', () => {
    it('should handle none request', async () => {
      const response = await request(app.getHttpServer())
        .put('/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect([200, 404]).toContain(response.status);
    });
  });

});
