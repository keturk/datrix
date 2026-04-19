import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('ShippingApi Internal Endpoints', () => {
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

  describe('POST /api/v1/shipments/ (internal)', () => {
    it('should handle internal post request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/shipments/')
        .set('X-Internal-Token', 'internal-service-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to post', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/shipments/')
        .expect(403);
    });
  });

});
