import {
  IsObject,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class FedExWebhookRequest {

  @ApiProperty()
  @IsObject()
  payload!: Record<string, any>;


}
