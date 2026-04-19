import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { UserLoggedInEvent } from './user-logged-in.event';

@EventsHandler(UserLoggedInEvent)
export class HandleUserLoggedInHandler implements IEventHandler<UserLoggedInEvent> {
  private readonly logger = new Logger(HandleUserLoggedInHandler.name);

  async handle(event: UserLoggedInEvent): Promise<void> {
console.info('user_logged_in');;
  }
}
