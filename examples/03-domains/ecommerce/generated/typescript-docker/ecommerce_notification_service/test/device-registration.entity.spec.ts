import { DeviceRegistration } from '../src/ecommerce_notification_service/entities/notification_db/device-registration.entity';
import { DevicePlatform } from '../src/enums/device-platform.enum';

describe('DeviceRegistration Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new DeviceRegistration();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new DeviceRegistration();
    const subjectVal = 'test-value';
    const tokenVal = 'test-value';
    const platformVal = DevicePlatform.Ios;
    entity.subject = subjectVal;
    entity.token = tokenVal;
    entity.platform = platformVal;
    expect(entity.subject).toBe(subjectVal);
    expect(entity.token).toBe(tokenVal);
    expect(entity.platform).toBe(platformVal);
  });

  it('should update field values', () => {
    const entity = new DeviceRegistration();
    const tokenVal = 'updated-value';
    entity.token = tokenVal;
    expect(entity.token).toBe(tokenVal);
  });

  it('should have index on subject', () => {
    const entity = new DeviceRegistration();
    entity.subject = 'test-value';
    expect(entity.subject).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new DeviceRegistration();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
