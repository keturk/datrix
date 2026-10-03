import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('PaymentController Auth', () => {
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

  describe('GET /api/v1/payments/00000000-0000-0000-0000-000000000001 (unauthenticated)', () => {
    it('should return 401 without auth token', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/payments/00000000-0000-0000-0000-000000000001')
        .expect(401);
    });
  });

});
