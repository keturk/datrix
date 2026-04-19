import { Shipment } from '../src/entities/shipment.entity';

describe('Shipment Functions', () => {
  describe('calculateDaysInTransit', () => {
    it('should be defined as a method', () => {
      const entity = new Shipment();
      expect(typeof entity.calculateDaysInTransit).toBe('function');
    });

    it('should accept 0 parameter(s)', () => {
      const entity = new Shipment();
      expect(entity.calculateDaysInTransit.length).toBe(0);
    });

    it('should return a value of the expected type', () => {
      const entity = new Shipment();
      const result = entity.calculateDaysInTransit(
      );
      expect(result).toBeDefined();
    });
  });

  describe('markDelivered', () => {
    it('should be defined as a method', () => {
      const entity = new Shipment();
      expect(typeof entity.markDelivered).toBe('function');
    });

    it('should accept 0 parameter(s)', () => {
      const entity = new Shipment();
      expect(entity.markDelivered.length).toBe(0);
    });

  });

  describe('markFailed', () => {
    it('should be defined as a method', () => {
      const entity = new Shipment();
      expect(typeof entity.markFailed).toBe('function');
    });

    it('should accept 1 parameter(s)', () => {
      const entity = new Shipment();
      expect(entity.markFailed.length).toBe(1);
    });

  });

});
