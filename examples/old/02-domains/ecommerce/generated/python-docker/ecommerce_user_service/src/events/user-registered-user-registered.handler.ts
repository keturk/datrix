import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { UserRegisteredEvent } from './user-registered.event';

@EventsHandler(UserRegisteredEvent)
export class HandleUserRegisteredHandler implements IEventHandler<UserRegisteredEvent> {
  private readonly logger = new Logger(HandleUserRegisteredHandler.name);

  async handle(event: UserRegisteredEvent): Promise<void> {
console.info('user_registered');;
  }
}
