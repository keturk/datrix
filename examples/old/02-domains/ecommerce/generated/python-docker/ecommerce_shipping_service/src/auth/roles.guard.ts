import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { ROLES_KEY } from './roles.decorator';

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRoles = this.reflector.getAllAndOverride<string[]>(
      ROLES_KEY,
      [context.getHandler(), context.getClass()],
    );
    if (!requiredRoles || requiredRoles.length === 0) {
      return true;
    }

    const request = context.switchToHttp().getRequest() as Record<
      string,
      unknown
    >;
    const user = request['user'] as Record<string, unknown> | undefined;
    if (!user) {
      return false;
    }

    const userRoles = (user['roles'] as string[]) ?? [];
    return requiredRoles.some((role) => userRoles.includes(role));
  }
}
