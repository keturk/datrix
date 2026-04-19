import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ShipmentController', () => {
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

  describe('GET /api/v1/shipments/shipments/:id', () => {
    it('should return a single shipment', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/shipments/shipments/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });

    it('should return 404 for non-existent shipment', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/shipments/shipments/00000000-0000-0000-0000-000000000099')
        .set('Authorization', 'Bearer test-token')
        .expect(404);
    });
  });

  describe('PATCH /api/v1/shipments/shipments/:id', () => {
    it('should update an existing shipment', async () => {
      const updateDto = {
        createdAt: new Date(),
        updatedAt: new Date(),
        orderId: '00000000-0000-0000-0000-000000000001',
        trackingNumber: 'test_value',
        carrier: 'test_value',
        status: 'test_value',
        destination: 'test_value',
        weight: 'test_value',
        estimatedDelivery: 'test_value',
        actualDelivery: 'test_value',
        failureReason: 'test_value',
      };

      const response = await request(app.getHttpServer())
        .patch('/api/v1/shipments/shipments/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .send(updateDto)
        .expect(200);

      expect(response.body).toHaveProperty('id');
    });
  });

});
