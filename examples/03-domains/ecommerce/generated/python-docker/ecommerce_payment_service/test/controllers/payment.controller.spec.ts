import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('PaymentController', () => {
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

  describe('GET /api/v1/payments/payments/:id', () => {
    it('should return a single payment', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/payments/payments/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });

    it('should return 404 for non-existent payment', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/payments/payments/00000000-0000-0000-0000-000000000099')
        .set('Authorization', 'Bearer test-token')
        .expect(404);
    });
  });

  describe('PATCH /api/v1/payments/payments/:id', () => {
    it('should update an existing payment', async () => {
      const updateDto = {
        createdAt: new Date(),
        updatedAt: new Date(),
        orderId: '00000000-0000-0000-0000-000000000001',
        customerId: '00000000-0000-0000-0000-000000000001',
        amount: 19.99,
        method: 'test_value',
        status: 'test_value',
        transactionId: 'test_value',
        gatewayResponse: 'test_value',
        errorMessage: 'test_value',
        processedAt: 'test_value',
      };

      const response = await request(app.getHttpServer())
        .patch('/api/v1/payments/payments/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .send(updateDto)
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });
  });

});
