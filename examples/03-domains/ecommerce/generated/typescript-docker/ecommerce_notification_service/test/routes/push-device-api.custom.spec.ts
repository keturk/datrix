import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { AppModule } from '../../src/app.module';

describe('PushDeviceApi Custom Endpoints', () => {
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

  describe('POST /push/devices?request=integration-path-value', () => {
    it('should handle postDevices request', async () => {
      const response = await request(app.getHttpServer())
        .post('/push/devices?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect(response.status).toBe(201);
    });
  });

  describe('POST /push/devices/unregister?request=integration-path-value', () => {
    it('should handle postDevicesUnregister request', async () => {
      const response = await request(app.getHttpServer())
        .post('/push/devices/unregister?request=integration-path-value')
        .set('Authorization', 'Bearer test-token')
        .send({});
      expect(response.status).toBe(201);
    });
  });

});
