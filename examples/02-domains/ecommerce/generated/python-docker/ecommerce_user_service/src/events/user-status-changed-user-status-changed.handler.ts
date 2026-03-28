import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { UserStatusChangedEvent } from './user-status-changed.event';

@EventsHandler(UserStatusChangedEvent)
export class HandleUserStatusChangedHandler implements IEventHandler<UserStatusChangedEvent> {
  private readonly logger = new Logger(HandleUserStatusChangedHandler.name);

  async handle(event: UserStatusChangedEvent): Promise<void> {
console.info('user_status_changed');;
  }
}
