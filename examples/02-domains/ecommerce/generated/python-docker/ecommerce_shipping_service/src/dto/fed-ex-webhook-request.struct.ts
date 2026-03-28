import {
  IsObject,
} from 'class-validator';

export class FedExWebhookRequest {

  @IsObject()
  payload!: Record<string, unknown>;


}
