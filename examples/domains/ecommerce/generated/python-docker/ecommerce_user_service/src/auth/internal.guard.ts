import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';

/**
 * Rejects requests that are not marked as internal (e.g. missing internal service token).
 * Wire this guard to match your platform's internal-auth mechanism.
 */
@Injectable()
export class InternalGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest() as Record<string, unknown>;
    const internal = request['internal'];
    if (internal === true) {
      return true;
    }
    throw new UnauthorizedException('Internal endpoint');
  }
}
