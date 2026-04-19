import { EventsHandler, IEventHandler } from '@nestjs/cqrs';
import { Logger } from '@nestjs/common';
import { UserVerifiedEvent } from './user-verified.event';

@EventsHandler(UserVerifiedEvent)
export class HandleUserVerifiedHandler implements IEventHandler<UserVerifiedEvent> {
  private readonly logger = new Logger(HandleUserVerifiedHandler.name);

  async handle(event: UserVerifiedEvent): Promise<void> {
console.info('user_verified');;
  }
}
