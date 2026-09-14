import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD, APP_FILTER } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_shipping_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { Shipment } from './ecommerce_shipping_service/entities/shipping_db/shipment.entity';
import { ShipmentEvent } from './ecommerce_shipping_service/entities/shipping_db/shipment-event.entity';
import { ShipmentItem } from './ecommerce_shipping_service/entities/shipping_db/shipment-item.entity';
import { ShippingDbDatabaseModule } from './shipping-db/database.module';
import { EntityLifecycleModule } from './entity-lifecycle.module';
import { PubsubModule as PubsubInst1 } from './mq/pubsub.module';
import { CqrsModule } from '@nestjs/cqrs';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { CacheHealthService } from './redis/cache.health';
import { ShippingAPIController } from './controllers/shipping_api.controller';
import { ShipmentService } from './services/shipment.service';
import { ShipmentEventService } from './services/shipment_event.service';
import { ShipmentItemService } from './services/shipment_item.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { getThrottlerModule } from './ecommerce_shipping_service/gateway-throttler.config';
import { JobsModule } from './jobs/jobs.module';
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
    ShippingDbDatabaseModule,
    MikroOrmModule.forFeature([
      Shipment,
      ShipmentEvent,
      ShipmentItem,
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
    ShippingAPIController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_GUARD, useClass: RateLimitGuard },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    CacheHealthService,
    ShipmentService,
    ShipmentEventService,
    ShipmentItemService,
  ],
})
export class AppModule {
}
