import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_GUARD } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_notification_service/secrets';
import { buildClient as buildRuntimeReadinessConfigClient, RemoteConfigClient } from './config/remoteConfig';
import { RuntimeReadinessController } from './config/runtime-readiness.controller';
import { MikroOrmModule } from '@mikro-orm/nestjs';
import { NotificationAudit } from './ecommerce_notification_service/entities/notification_db/notification-audit.entity';
import { NotificationDbDatabaseModule } from './notification-db/database.module';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { NotificationAuditService } from './services/notification_audit.service';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { getThrottlerModule } from './ecommerce_notification_service/gateway-throttler.config';
import { HttpClientsModule } from './http-clients.module';
import { InternalGuard } from './discovery/internal-guard';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    SecretsModule,
    NotificationDbDatabaseModule,
    MikroOrmModule.forFeature([
      NotificationAudit,
    ]),
    getThrottlerModule(),
    LoggerModule,
    HttpClientsModule,
  ],
  controllers: [
    MetricsController,
    HealthController,
    RuntimeReadinessController,
  ],
  providers: [
    { provide: RemoteConfigClient, useFactory: buildRuntimeReadinessConfigClient },
    { provide: APP_GUARD, useClass: InternalGuard },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
    NotificationAuditService,
  ],
})
export class AppModule {
}
