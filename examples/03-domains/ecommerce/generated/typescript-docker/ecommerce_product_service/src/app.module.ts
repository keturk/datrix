import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD, APP_FILTER } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_product_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { Category } from './ecommerce_product_service/entities/product_db/category.entity';
import { Product } from './ecommerce_product_service/entities/product_db/product.entity';
import { InventoryReservation } from './ecommerce_product_service/entities/product_db/inventory-reservation.entity';
import { ProductDbDatabaseModule } from './product-db/database.module';
import { NosqlDatabaseModule as DocdbNosqlDatabaseModule } from './nosql/nosql-database.module';
import { NosqlModule as DocdbNosqlModule } from './nosql/nosql.module';
import { EntityLifecycleModule } from './entity-lifecycle.module';
import { PubsubModule as PubsubInst1 } from './mq/pubsub.module';
import { CqrsModule } from '@nestjs/cqrs';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { CacheHealthService } from './redis/cache.health';
import { ProductAPIController } from './controllers/product_api.controller';
import { CategoryService } from './services/category.service';
import { ProductService } from './services/product.service';
import { InventoryReservationService } from './services/inventory_reservation.service';
import { StoreStorageService } from './store/storage.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { getThrottlerModule } from './ecommerce_product_service/gateway-throttler.config';
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
    ProductDbDatabaseModule,
    MikroOrmModule.forFeature([
      Category,
      Product,
      InventoryReservation,
    ]),
    DocdbNosqlDatabaseModule,
    DocdbNosqlModule,
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
    ProductAPIController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_GUARD, useClass: RateLimitGuard },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    CacheHealthService,
    CategoryService,
    ProductService,
    InventoryReservationService,
    StoreStorageService,
  ],
})
export class AppModule {
}
