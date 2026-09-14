import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD, APP_FILTER } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_payment_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { Payment } from './ecommerce_payment_service/entities/payment_db/payment.entity';
import { Refund } from './ecommerce_payment_service/entities/payment_db/refund.entity';
import { PaymentDbDatabaseModule } from './payment-db/database.module';
import { EntityLifecycleModule } from './entity-lifecycle.module';
import { PubsubModule as PubsubInst1 } from './mq/pubsub.module';
import { CqrsModule } from '@nestjs/cqrs';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { PaymentAPIController } from './controllers/payment_api.controller';
import { PaymentService } from './services/payment.service';
import { RefundService } from './services/refund.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { getThrottlerModule } from './ecommerce_payment_service/gateway-throttler.config';
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
    PaymentDbDatabaseModule,
    MikroOrmModule.forFeature([
      Payment,
      Refund,
    ]),
    EntityLifecycleModule,
    PubsubInst1,
    CqrsModule.forRoot(),
    getThrottlerModule(),
    LoggerModule,
    HttpClientsModule,
  ],
  controllers: [
    MetricsController,
    HealthController,
    RuntimeReadinessController,
    PaymentAPIController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_GUARD, useClass: InternalGuard },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    PaymentService,
    RefundService,
    FunctionsService,
  ],
})
export class AppModule {
}
