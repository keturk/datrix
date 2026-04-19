import { Injectable, Logger } from '@nestjs/common';
import { UserLoggedInEvent } from './user-logged-in.event';
import type { UserLoggedInPayload } from '../mq/schemas';
import { UserRegisteredEvent } from './user-registered.event';
import type { UserRegisteredPayload } from '../mq/schemas';
import { UserStatusChangedEvent } from './user-status-changed.event';
import type { UserStatusChangedPayload } from '../mq/schemas';
import { UserVerifiedEvent } from './user-verified.event';
import type { UserVerifiedPayload } from '../mq/schemas';

@Injectable()
export class UserServiceEventPublisher {
  private readonly logger = new Logger(UserServiceEventPublisher.name);

  constructor(private readonly eventBus: { publish: (event: unknown) => Promise<void> }) {}

  async publishUserLoggedIn(payload: Partial<UserLoggedInPayload>): Promise<void> {
    this.logger.log(`Publishing UserLoggedIn`);
    await this.eventBus.publish(new UserLoggedInEvent(payload as UserLoggedInPayload));
  }
  async publishUserRegistered(payload: Partial<UserRegisteredPayload>): Promise<void> {
    this.logger.log(`Publishing UserRegistered`);
    await this.eventBus.publish(new UserRegisteredEvent(payload as UserRegisteredPayload));
  }
  async publishUserStatusChanged(payload: Partial<UserStatusChangedPayload>): Promise<void> {
    this.logger.log(`Publishing UserStatusChanged`);
    await this.eventBus.publish(new UserStatusChangedEvent(payload as UserStatusChangedPayload));
  }
  async publishUserVerified(payload: Partial<UserVerifiedPayload>): Promise<void> {
    this.logger.log(`Publishing UserVerified`);
    await this.eventBus.publish(new UserVerifiedEvent(payload as UserVerifiedPayload));
  }
}
