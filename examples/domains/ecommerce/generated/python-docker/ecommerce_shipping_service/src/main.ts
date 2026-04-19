import './observability/tracing';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { startScheduler, stopScheduler } from './jobs/scheduler';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors({
    origin: ["*"],
    methods: ["GET", "POST", "PUT", "DELETE", "PATCH"],
    allowedHeaders: ["Content-Type", "Authorization"],
    credentials: true,
    maxAge: 3600,
  });
  startScheduler();
  process.on('SIGTERM', stopScheduler);
  process.on('SIGINT', stopScheduler);
  await app.listen(process.env.PORT ?? 3000);
}
bootstrap();
