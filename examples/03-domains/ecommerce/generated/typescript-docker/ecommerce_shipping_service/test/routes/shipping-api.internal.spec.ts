import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ShippingApi Internal Endpoints', () => {
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

  describe('POST /api/v1/shipments/?request=integration-path-value (internal)', () => {
    it('should handle internal createShipment request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/shipments/?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to createShipment', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/shipments/?request=integration-path-value')
        .expect(403);
    });
  });

});
