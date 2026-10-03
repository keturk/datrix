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
    it('should handle internal postEndpoint request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/shipments/?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to postEndpoint', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/shipments/?request=integration-path-value')
        .expect(401);
    });

    it('should reject a credential from a provider outside the route allow-list for postEndpoint', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/shipments/?request=integration-path-value')
        .set('Authorization', 'Bearer wrong-provider-token')
        .expect(403);
    });
  });

});
