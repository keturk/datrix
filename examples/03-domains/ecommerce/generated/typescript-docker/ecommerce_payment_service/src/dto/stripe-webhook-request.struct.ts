import {
  IsObject,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class StripeWebhookRequest {

  @ApiProperty()
  @IsObject()
  payload!: Record<string, any>;


}
