import { Test, TestingModule } from '@nestjs/testing';
import { OrderApiController } from '../../src/controllers/order-api.controller';

describe('OrderApi Functions', () => {
  let controller: OrderApiController;

  beforeAll(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [OrderApiController],
    }).compile();

    controller = module.get<OrderApiController>(OrderApiController);
  });

  describe('checkIdempotency', () => {
    it('should be defined', () => {
      expect(controller.checkIdempotency).toBeDefined();
    });

    it('should return a value', async () => {
      const result = await controller.checkIdempotency(undefined, undefined);
      expect(result).toBeDefined();
    });
  });

  describe('storeIdempotency', () => {
    it('should be defined', () => {
      expect(controller.storeIdempotency).toBeDefined();
    });

  });

});
