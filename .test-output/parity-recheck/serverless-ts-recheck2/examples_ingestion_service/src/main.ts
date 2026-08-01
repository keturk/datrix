import './observability/tracing';
import { NestFactory } from '@nestjs/core';
import { CallHandler, ExecutionContext, NestInterceptor, ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';
import { SwaggerModule, DocumentBuilder } from '@nestjs/swagger';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { RemoteConfigClient } from './config/remoteConfig';

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

/**
 * Recursively convert object keys from snake_case to camelCase.
 * Used to normalise incoming JSON request bodies so that NestJS DTOs
 * (which use camelCase property names) accept snake_case payloads.
 */
function camelizeKeys(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(camelizeKeys);
  if (obj !== null && typeof obj === 'object' && !(obj instanceof Date)) {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k.replace(/_([a-z])/g, (_: string, c: string) => c.toUpperCase()),
        camelizeKeys(v),
      ]),
    );
  }
  return obj;
}

/**
 * Recursively convert object keys from camelCase to snake_case.
 * Used to normalise outgoing JSON response bodies so that API consumers
 * receive the standard snake_case field names defined in the .dtrx schema.
 */
function snakeizeKeys(obj: unknown): unknown {
  if (Array.isArray(obj)) {
    return obj.map(snakeizeKeys);
  }
  if (obj instanceof Date) {
    return obj;
  }
  if (typeof Buffer !== 'undefined' && obj instanceof Buffer) {
    return obj;
  }
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([k, v]) => [
        k.replace(/[A-Z]/g, (c: string) => `_${c.toLowerCase()}`),
        snakeizeKeys(v),
      ]),
    );
  }
  return obj;
}

class SnakeCaseResponseInterceptor implements NestInterceptor {
  intercept(_context: ExecutionContext, next: CallHandler): Observable<unknown> {
    return next.handle().pipe(map((data: unknown) => snakeizeKeys(data)));
  }
}

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { rawBody: true });

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
    .setTitle('examples.IngestionService API')
    .setDescription('Auto-generated API documentation for examples.IngestionService')
    .setVersion('1.0')
    .addBearerAuth()
    .build();
  const document = SwaggerModule.createDocument(app, config);
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

  app.useGlobalPipes(new ValidationPipe({
    whitelist: true,
    forbidNonWhitelisted: true,
    transform: true,
    errorHttpStatusCode: 422,
  }));

  await app.listen(process.env.PORT ?? 3000);
}
bootstrap().catch((err) => fatal('Application failed to start', err));
