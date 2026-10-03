import { DeviceRegistration } from '../../src/entities/device-registration.entity';
import { DevicePlatform } from '../../src/enums/device-platform.enum';

/**
 * Build a partial DeviceRegistration with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildDeviceRegistration(
  overrides?: Partial<DeviceRegistration>,
): Partial<DeviceRegistration> {
  return {
    subject: 'test',
    token: 'test',
    platform: DevicePlatform.Ios,
    ...overrides,
  };
}
