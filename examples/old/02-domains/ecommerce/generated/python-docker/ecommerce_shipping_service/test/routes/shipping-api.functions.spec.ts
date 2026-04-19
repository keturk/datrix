import { Test, TestingModule } from '@nestjs/testing';
import { ShippingApiController } from '../../src/controllers/shipping-api.controller';

describe('ShippingApi Functions', () => {
  let controller: ShippingApiController;

  beforeAll(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [ShippingApiController],
    }).compile();

    controller = module.get<ShippingApiController>(ShippingApiController);
  });

  describe('calculateRate', () => {
    it('should be defined', () => {
      expect(controller.calculateRate).toBeDefined();
    });

    it('should return a value', async () => {
      const result = await controller.calculateRate(undefined, undefined, undefined);
      expect(result).toBeDefined();
    });
  });

  describe('mapFedExStatus', () => {
    it('should be defined', () => {
      expect(controller.mapFedExStatus).toBeDefined();
    });

    it('should return a value', async () => {
      const result = await controller.mapFedExStatus(undefined);
      expect(result).toBeDefined();
    });
  });

});
