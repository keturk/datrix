import { SetMetadata } from '@nestjs/common';

export const ROLES_KEY = 'roles';

/**
 * Specify required roles for a route handler (flat any-of). AuthGuard reads
 * this metadata and answers 403 when the principal holds none of the roles.
 *
 * Usage:
 * ```typescript
 * @Roles('admin', 'moderator')
 * @Get('admin')
 * adminOnly() { ... }
 * ```
 */
export const Roles = (...roles: string[]) => SetMetadata(ROLES_KEY, roles);
