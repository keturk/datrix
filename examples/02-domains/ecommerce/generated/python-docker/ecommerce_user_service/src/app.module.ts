import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { APP_GUARD } from '@nestjs/core';
import configuration from './config/configuration';
import { SecretsModule } from './ecommerce_user_service/secrets';
import { DbDatabaseModule } from './db/database.module';
import { EntityLifecycleModule } from './entity-lifecycle.module';
import { PubsubModule as PubsubInst1 } from './mq/pubsub.module';
import { MetricsController } from './observability/metrics.controller';
import { HealthController } from './observability/health.controller';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { MetricsInterceptor } from './observability/metrics.interceptor';
import { LoggerModule } from './observability/logger.module';
import { JwtModule } from '@nestjs/jwt';
import { JwtAuthGuard } from './ecommerce_user_service/gateway-auth.guard';
import { getThrottlerModule } from './ecommerce_user_service/gateway-throttler.config';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true, load: [configuration] }),
    SecretsModule,
    DbDatabaseModule,
    EntityLifecycleModule,
    PubsubInst1,
    JwtModule.registerAsync({
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => ({
        secret: config.getOrThrow<string>('jwtSecret'),
        signOptions: {
          algorithm: 'HS256',
          issuer: 'ecommerce-user-service',
        },
      }),
    }),
    getThrottlerModule(),
    LoggerModule,
  ],
  controllers: [
    MetricsController,
    HealthController,
  ],
  providers: [
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_INTERCEPTOR, useClass: MetricsInterceptor },
  ],
})
export class AppModule {}
