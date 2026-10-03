import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ProductApi Internal Endpoints', () => {
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

  describe('POST /api/v1/products/service/check-availability?request=integration-path-value (internal)', () => {
    it('should handle internal postServiceCheckAvailability request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/check-availability?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to postServiceCheckAvailability', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/check-availability?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postServiceCheckAvailability', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/check-availability?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/service/reserve-inventory?request=integration-path-value (internal)', () => {
    it('should handle internal postServiceReserveInventory request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/reserve-inventory?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to postServiceReserveInventory', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/reserve-inventory?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postServiceReserveInventory', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/reserve-inventory?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/service/confirm-reservation?request=integration-path-value (internal)', () => {
    it('should handle internal postServiceConfirmReservation request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/confirm-reservation?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to postServiceConfirmReservation', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/confirm-reservation?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postServiceConfirmReservation', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/confirm-reservation?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/service/release-reservation?request=integration-path-value (internal)', () => {
    it('should handle internal postServiceReleaseReservation request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/release-reservation?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to postServiceReleaseReservation', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/release-reservation?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postServiceReleaseReservation', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/release-reservation?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

  describe('GET /api/v1/products/service/00000000-0000-0000-0000-000000000001 (internal)', () => {
    it('should handle internal getServiceById request', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/products/service/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(404);
    });

    it('should reject external access to getServiceById', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/products/service/00000000-0000-0000-0000-000000000001')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for getServiceById', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/products/service/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

  describe('POST /api/v1/products/service/bulk?request=integration-path-value (internal)', () => {
    it('should handle internal postServiceBulk request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/bulk?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to postServiceBulk', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/bulk?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postServiceBulk', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/products/service/bulk?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

});
