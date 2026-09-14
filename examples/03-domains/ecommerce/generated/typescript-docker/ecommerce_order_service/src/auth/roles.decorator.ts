import { SetMetadata } from '@nestjs/common';

export const ROLES_KEY = 'roles';

/**
 * Specify required roles for a route handler.
 *
 * Usage:
 * ```typescript
 * @Roles('admin', 'moderator')
 * @UseGuards(RolesGuard)
 * @Get('admin')
 * adminOnly() { ... }
 * ```
 */
export const Roles = (...roles: string[]) => SetMetadata(ROLES_KEY, roles);
