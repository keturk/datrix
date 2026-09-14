import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD, APP_FILTER } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_user_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { User } from './ecommerce_user_service/entities/user_db/user.entity';
import { UserSession } from './ecommerce_user_service/entities/user_db/user-session.entity';
import { UserPreferences } from './ecommerce_user_service/entities/user_db/user-preferences.entity';
import { UserDbDatabaseModule } from './user-db/database.module';
import { EntityLifecycleModule } from './entity-lifecycle.module';
import { PubsubModule as PubsubInst1 } from './mq/pubsub.module';
import { CqrsModule } from '@nestjs/cqrs';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { CacheHealthService } from './redis/cache.health';
import { UserAPIController } from './controllers/user_api.controller';
import { UserService } from './services/user.service';
import { UserSessionService } from './services/user_session.service';
import { UserPreferencesService } from './services/user_preferences.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { getThrottlerModule } from './ecommerce_user_service/gateway-throttler.config';
import { RateLimitGuard } from './rate-limit/rate-limit.guard';
import { RateLimitModule } from './rate-limit/rate-limit.module';
import { HttpClientsModule } from './http-clients.module';
import { AllExceptionsFilter } from './errors/all-exceptions-filter';
import { EventEmitterModule } from '@nestjs/event-emitter';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    SecretsModule,
    EventEmitterModule.forRoot(),
    UserDbDatabaseModule,
    MikroOrmModule.forFeature([
      User,
      UserSession,
      UserPreferences,
    ]),
    EntityLifecycleModule,
    PubsubInst1,
    CqrsModule.forRoot(),
    getThrottlerModule(),
    LoggerModule,
    RateLimitModule,
    HttpClientsModule,
  ],
  controllers: [
    MetricsController,
    HealthController,
    RuntimeReadinessController,
    UserAPIController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_GUARD, useClass: RateLimitGuard },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    CacheHealthService,
    UserService,
    UserSessionService,
    UserPreferencesService,
  ],
})
export class AppModule {
}
