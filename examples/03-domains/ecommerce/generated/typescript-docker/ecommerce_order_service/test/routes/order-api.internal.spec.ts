import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('OrderApi Internal Endpoints', () => {
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

  describe('GET /api/v1/orders/service/00000000-0000-0000-0000-000000000001 (internal)', () => {
    it('should handle internal getServiceById request', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/orders/service/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(404);
    });

    it('should reject external access to getServiceById', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/orders/service/00000000-0000-0000-0000-000000000001')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for getServiceById', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/orders/service/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

  describe('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment?request=integration-path-value (internal)', () => {
    it('should handle internal postByIdConfirmPayment request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(404);
    });

    it('should reject external access to postByIdConfirmPayment', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postByIdConfirmPayment', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

  describe('POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment?request=integration-path-value (internal)', () => {
    it('should handle internal postByIdUpdateShipment request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(404);
    });

    it('should reject external access to postByIdUpdateShipment', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postByIdUpdateShipment', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

});
