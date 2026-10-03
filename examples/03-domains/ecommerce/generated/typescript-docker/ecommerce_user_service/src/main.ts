import './observability/tracing';
import { NestFactory } from '@nestjs/core';
import {
  CallHandler,
  ExecutionContext,
  NestInterceptor,
  UnprocessableEntityException,
  ValidationPipe,
} from '@nestjs/common';
import type { ValidationError } from 'class-validator';
import { EntityManager } from '@mikro-orm/core';
import { loadIdentityPlanAtStartup } from './auth/identity';
import { bindApiKeyStoreEntityManager, bindApiKeyRateLimitRedis } from './auth/api-key-verify';
import { RedisCacheConnection as RedisRateLimitConnection } from './redis/connection';
import { AppModule } from './app.module';
import { camelizeKeys, snakeizeKeys } from './support/key-transform';
import { requestContextMiddleware } from './ecommerce_user_service/_requestContext';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { RemoteConfigClient } from './config/remoteConfig';
import { startRedisConnectionConfig } from './config/redisConnection';
import { ChangePasswordRequest } from './dto/change-password-request.struct';
import { ForgotPasswordRequest } from './dto/forgot-password-request.struct';
import { IssueApiKeyRequest } from './dto/issue-api-key-request.struct';
import { IssueApiKeyResponse } from './dto/issue-api-key-response.struct';
import { LoginRequest } from './dto/login-request.struct';
import { LoginResponse } from './dto/login-response.struct';
import { LogoutRequest } from './dto/logout-request.struct';
import { RegisterRequest } from './dto/register-request.struct';
import { ResetPasswordRequest } from './dto/reset-password-request.struct';
import { SessionValidationResponse } from './dto/session-validation-response.struct';
import { UpdateProfileRequest } from './dto/update-profile-request.struct';
import { UpdateUserStatusRequest } from './dto/update-user-status-request.struct';
import { ValidateSessionRequest } from './dto/validate-session-request.struct';
import { VerifyEmailRequest } from './dto/verify-email-request.struct';
import { ApiKeyVerifyRequest } from './dto/api-key-verify-request.struct';

/**
 * Write an error message to stderr and exit. Uses process.stderr.write()
 * with a callback to ensure the message is flushed to the Docker log driver
 * before process.exit() terminates the event loop. In non-TTY mode (Docker
 * detached containers), console.error() is block-buffered and process.exit()
 * kills the process before the buffer flushes — losing the error message.
 */
function fatal(label: string, err: unknown): void {
  const msg = err instanceof Error ? err.stack ?? err.message : String(err);
  process.stderr.write(`${label}: ${msg}\n`, () => process.exit(1));
  setTimeout(() => process.exit(1), 1000).unref();
}

// Process-level error handlers — ensure crashes are always logged,
// even when they bypass bootstrap().catch().
process.on('uncaughtException', (err) => fatal('FATAL uncaughtException', err));
process.on('unhandledRejection', (reason) => fatal('FATAL unhandledRejection', reason));
process.on('exit', (code) => {
  console.error(`Process exit code=${code} rss=${Math.round(process.memoryUsage().rss / 1024 / 1024)}MB`);
});
// Runtime config-store client, constructed and started during bootstrap and
// stopped on shutdown so the background poll timer is torn down cleanly.
let remoteConfigClient: RemoteConfigClient | null = null;
process.on('SIGTERM', () => {
  remoteConfigClient?.stop();
  process.stderr.write('Received SIGTERM\n', () => process.exit(143));
  setTimeout(() => process.exit(143), 1000).unref();
});

class SnakeCaseResponseInterceptor implements NestInterceptor {
  intercept(_context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(map((data: unknown) => snakeizeKeys(data)));
  }
}

/**
 * Recursively flatten class-validator's `ValidationError` tree (`property` +
 * `children`) into wire-ready field errors: a dotted path relative to the
 * request body root, with `[n]` for a numeric-string `property` (an
 * array-index child) -- the one field-error path shape every realized
 * Datrix target answers with. class-validator's own tree never carries a
 * leading `body` segment (it starts at the DTO's own properties), so there
 * is nothing to strip here.
 */
function buildValidationFieldErrors(
  errors: ValidationError[],
  parentPath = '',
): { field: string; message: string }[] {
  const fieldErrors: { field: string; message: string }[] = [];
  for (const error of errors) {
    const isArrayIndex = /^\d+$/.test(error.property);
    let path: string;
    if (isArrayIndex) {
      path = `${parentPath}[${error.property}]`;
    } else if (parentPath) {
      path = `${parentPath}.${error.property}`;
    } else {
      path = error.property;
    }
    if (error.constraints) {
      for (const message of Object.values(error.constraints)) {
        fieldErrors.push({ field: path, message });
      }
    }
    if (error.children && error.children.length > 0) {
      fieldErrors.push(...buildValidationFieldErrors(error.children, path));
    }
  }
  return fieldErrors;
}

async function bootstrap() {
  // Load the identity provider plan before anything serves: a missing,
  // unreadable or unsupported plan aborts startup here instead of turning
  // every authenticated request into a 401.
  loadIdentityPlanAtStartup();
  // Load the Redis connection facts from the runtime config store before any
  // module opens a Redis client; an unreadable store aborts startup here.
  await startRedisConnectionConfig();
  const app = await NestFactory.create(AppModule, { rawBody: true });

  // Ambient request context (Request.* accessors reached from service
  // functions). Registered first, so it is the OUTERMOST layer: the binding
  // exists before any other middleware, guard, or handler runs on the request.
  app.use(requestContextMiddleware);

  // Bind, per API-key provider this service stores, the EntityManager of the
  // block holding its keys and -- when a per-key rate limit is mapped -- the
  // Redis client of its rate-limit cache, so the verify route and in-process
  // key resolution share one verification path.
  bindApiKeyStoreEntityManager("customerKeys", app.get(EntityManager));
  const redisRateLimitConnection = new RedisRateLimitConnection().getClient();
  bindApiKeyRateLimitRedis("customerKeys", redisRateLimitConnection);

  // Start the runtime config-store client before the app begins serving so
  // feature flags / tuning values are available to request handlers. The client
  // honors failOpen: a failed initial refresh falls back to generated defaults
  // when failOpen is true, and aborts startup when failOpen is false.
  //
  // Assigned through a local const rather than read back off the module-level
  // `remoteConfigClient` let: that variable is captured by the SIGTERM closure
  // above, and a closure capture defeats TypeScript's control-flow narrowing
  // for every later read in this function -- `remoteConfigClient!.start()`
  // right after the assignment would still type-check as `| null`. The local
  // const is never captured, so it stays narrowed to the non-null type.
  // Retrieved from the Nest DI container (registered in AppModule) rather than
  // built standalone, so the runtime-readiness route/CLI probe the SAME
  // instance this bootstrap starts -- never a second, independently
  // constructed client that would silently diverge in cache state.
  const startedRemoteConfigClient = app.get(RemoteConfigClient);
  remoteConfigClient = startedRemoteConfigClient;
  await startedRemoteConfigClient.start();

  // Configure Swagger/OpenAPI documentation
  const config = new DocumentBuilder()
    .setTitle('ecommerce.UserService API')
    .setDescription('Auto-generated API documentation for ecommerce.UserService')
    .setVersion('1.0')
    .addBearerAuth()
    .build();
  const document = SwaggerModule.createDocument(app, config, {
    extraModels: [ChangePasswordRequest, ForgotPasswordRequest, IssueApiKeyRequest, IssueApiKeyResponse, LoginRequest, LoginResponse, LogoutRequest, RegisterRequest, ResetPasswordRequest, SessionValidationResponse, UpdateProfileRequest, UpdateUserStatusRequest, ValidateSessionRequest, VerifyEmailRequest, ApiKeyVerifyRequest],
  });
  SwaggerModule.setup('docs', app, document, {
    jsonDocumentUrl: '/openapi.json',
  });

  // Transform incoming request body keys from snake_case to camelCase
  // so that DTOs (camelCase properties) accept snake_case JSON payloads.
  const expressApp = app.getHttpAdapter().getInstance();
  expressApp.use((req: { body?: unknown }, _res: unknown, next: () => void) => {
    if (req.body && typeof req.body === 'object') {
      req.body = camelizeKeys(req.body);
    }
    next();
  });

  // Transform outgoing response body keys from camelCase to snake_case.
  app.useGlobalInterceptors(new SnakeCaseResponseInterceptor());

  // A custom exceptionFactory replaces NestJS's default (which flattens each
  // ValidationError into a plain message string, discarding the structured
  // property/children tree): building the field path here, from the
  // validator's own tree, is the only way AllExceptionsFilter can answer
  // errors[].field with the request's actual property path rather than a
  // guess at the first word of a message.
  app.useGlobalPipes(new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
    errorHttpStatusCode: 422,
    exceptionFactory: (errors: ValidationError[]) =>
      new UnprocessableEntityException(buildValidationFieldErrors(errors)),
  }));

  app.enableCors({
    origin: ["*"],
    methods: ["GET", "POST", "PUT", "DELETE", "PATCH"],
    allowedHeaders: ["Content-Type", "Authorization"],
    credentials: true,
    maxAge: 3600,
  });
  await app.listen(process.env.PORT ?? 3000);
}
bootstrap().catch((err) => fatal('Application failed to start', err));
