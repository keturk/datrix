import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { APP_GUARD, APP_FILTER } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './examples_order_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { Order } from './examples_order_service/entities/db/order.entity';
import { DbDatabaseModule } from './db/database.module';
import { PubsubModule as PubsubInst1 } from './mq/pubsub.module';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { OrderApiController } from './controllers/order_api.controller';
import { OrderService } from './services/order.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { JwtAuthGuard } from './examples_order_service/gateway-auth.guard';
import { getThrottlerModule } from './examples_order_service/gateway-throttler.config';
import { JobsModule } from './jobs/jobs.module';
import { HttpClientsModule } from './http-clients.module';
import { InternalGuard } from './discovery/internal-guard';
import { AllExceptionsFilter } from './errors/all-exceptions-filter';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    SecretsModule,
    DbDatabaseModule,
    MikroOrmModule.forFeature([
      Order,
    ]),
    PubsubInst1,
    getThrottlerModule(),
    LoggerModule,
    JobsModule,
    HttpClientsModule,
  ],
  controllers: [
    MetricsController,
    HealthController,
    RuntimeReadinessController,
    OrderApiController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_GUARD, useClass: InternalGuard },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    OrderService,
  ],
})
export class AppModule {
}
