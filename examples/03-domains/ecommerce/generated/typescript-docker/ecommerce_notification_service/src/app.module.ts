import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD, APP_FILTER } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_notification_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { NotificationAudit } from './ecommerce_notification_service/entities/notification_db/notification-audit.entity';
import { DeviceRegistration } from './ecommerce_notification_service/entities/notification_db/device-registration.entity';
import { NotificationDbDatabaseModule } from './notification-db/database.module';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { PushDeviceApiController } from './controllers/push_device_api.controller';
import { NotificationAuditService } from './services/notification_audit.service';
import { DeviceRegistrationService } from './services/device_registration.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { GatewayJwtVerifyController } from './ecommerce_notification_service/gateway-jwt-verify.controller';
import { getThrottlerModule } from './ecommerce_notification_service/gateway-throttler.config';
import { HttpClientsModule } from './http-clients.module';
import { AllExceptionsFilter } from './errors/all-exceptions-filter';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    SecretsModule,
    NotificationDbDatabaseModule,
    MikroOrmModule.forFeature([
      NotificationAudit,
      DeviceRegistration,
    ]),
    getThrottlerModule(),
    LoggerModule,
    HttpClientsModule,
  ],
  controllers: [
    MetricsController,
    HealthController,
    RuntimeReadinessController,
    GatewayJwtVerifyController,
    PushDeviceApiController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_FILTER, useClass: AllExceptionsFilter },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    NotificationAuditService,
    DeviceRegistrationService,
  ],
})
export class AppModule {
}
