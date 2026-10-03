import { SetMetadata } from '@nestjs/common';

/** Metadata key read by AuthGuard: an absent credential is served as anonymous. */
export const OPTIONAL_AUTH_KEY = 'optional_auth';

/**
 * Mark a route or controller as `auth(optional)`: a request with no
 * `Authorization` header is served with no `request.user`; a request that
 * presents a credential runs the full auth chain and is refused (401) when the
 * credential fails verification.
 */
export const OptionalAuth = () => SetMetadata(OPTIONAL_AUTH_KEY, true);

/** Metadata key read by AuthGuard for the route's principal-type allow-list. */
export const PRINCIPAL_TYPES_KEY = 'principal_types';

/**
 * Restrict a route to principals whose provider declares one of the listed
 * principal types (for example 'human' or 'machine'). AuthGuard answers 403
 * for a verified principal of any other type.
 *
 * @example
 * @PrincipalTypes('machine')
 */
export const PrincipalTypes = (...types: string[]) => SetMetadata(PRINCIPAL_TYPES_KEY, types);
