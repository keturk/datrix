import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD, APP_FILTER } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_order_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { Order } from './ecommerce_order_service/entities/order_db/order.entity';
import { OrderItem } from './ecommerce_order_service/entities/order_db/order-item.entity';
import { IdempotencyKey } from './ecommerce_order_service/entities/order_db/idempotency-key.entity';
import { OrderDbDatabaseModule } from './order-db/database.module';
import { EntityLifecycleModule } from './entity-lifecycle.module';
import { PubsubModule as PubsubInst1 } from './mq/pubsub.module';
import { CqrsModule } from '@nestjs/cqrs';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { CacheHealthService } from './redis/cache.health';
import { OrderAPIController } from './controllers/order_api.controller';
import { OrderService } from './services/order.service';
import { OrderItemService } from './services/order_item.service';
import { IdempotencyKeyService } from './services/idempotency_key.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { GatewayJwtVerifyController } from './ecommerce_order_service/gateway-jwt-verify.controller';
import { getThrottlerModule } from './ecommerce_order_service/gateway-throttler.config';
import { JobsModule } from './jobs/jobs.module';
import { RateLimitGuard } from './rate-limit/rate-limit.guard';
import { RateLimitModule } from './rate-limit/rate-limit.module';
import { HttpClientsModule } from './http-clients.module';
import { InternalGuard } from './discovery/internal-guard';
import { AllExceptionsFilter } from './errors/all-exceptions-filter';
import { FunctionsService } from './functions';
import { EventEmitterModule } from '@nestjs/event-emitter';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    SecretsModule,
    EventEmitterModule.forRoot(),
    OrderDbDatabaseModule,
    MikroOrmModule.forFeature([
      Order,
      OrderItem,
      IdempotencyKey,
    ]),
    EntityLifecycleModule,
    PubsubInst1,
    CqrsModule.forRoot(),
    getThrottlerModule(),
    LoggerModule,
    JobsModule,
    RateLimitModule,
    HttpClientsModule,
  ],
  controllers: [
    MetricsController,
    HealthController,
    RuntimeReadinessController,
    GatewayJwtVerifyController,
    OrderAPIController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_GUARD, useClass: InternalGuard },
    { provide: APP_GUARD, useClass: RateLimitGuard },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    CacheHealthService,
    OrderService,
    OrderItemService,
    IdempotencyKeyService,
    FunctionsService,
  ],
})
export class AppModule {
}
