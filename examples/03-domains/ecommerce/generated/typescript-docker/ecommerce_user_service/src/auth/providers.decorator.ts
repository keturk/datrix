import { SetMetadata } from '@nestjs/common';

/** Metadata key read by AuthGuard for the route's provider allow-list. */
export const PROVIDERS_KEY = 'identity_providers';

/**
 * Restrict a route to tokens issued by the listed identity providers.
 * AuthGuard answers 403 for a token from any other provider.
 *
 * @example
 * @Providers('customer', 'workforce')
 */
export const Providers = (...providers: string[]) => SetMetadata(PROVIDERS_KEY, providers);
