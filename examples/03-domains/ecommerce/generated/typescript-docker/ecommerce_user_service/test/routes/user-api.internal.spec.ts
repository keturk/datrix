import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('UserApi Internal Endpoints', () => {
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

  describe('GET /api/v1/service/00000000-0000-0000-0000-000000000001 (internal)', () => {
    it('should handle internal userByIdInternal request', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/service/00000000-0000-0000-0000-000000000001')
        .set('Authorization', 'Bearer test-token')
        .expect(404);
    });

    it('should reject external access to userByIdInternal', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/service/00000000-0000-0000-0000-000000000001')
        .expect(403);
    });
  });

  describe('POST /api/v1/service/validate-session?request=integration-path-value (internal)', () => {
    it('should handle internal sessionValidation request', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/service/validate-session?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({})
        .expect(201);
    });

    it('should reject external access to sessionValidation', async () => {
      await request(app.getHttpServer())
        .post('/api/v1/service/validate-session?request=integration-path-value')
        .expect(403);
    });
  });

});
