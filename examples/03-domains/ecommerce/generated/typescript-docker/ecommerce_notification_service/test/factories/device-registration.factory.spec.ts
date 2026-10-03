import { buildDeviceRegistration } from './device-registration.factory';

describe('buildDeviceRegistration', () => {
  it('should return a valid partial entity', () => {
    const result = buildDeviceRegistration();
    expect(result).toBeDefined();
    expect(result.subject).toBeDefined();
    expect(result.token).toBeDefined();
    expect(result.platform).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      subject: 'test',
    };
    const result = buildDeviceRegistration(overrides);
    expect(result.subject).toBe(overrides.subject);
  });

  it('should produce different instances', () => {
    const a = buildDeviceRegistration();
    const b = buildDeviceRegistration();
    expect(a).not.toBe(b);
  });
});
