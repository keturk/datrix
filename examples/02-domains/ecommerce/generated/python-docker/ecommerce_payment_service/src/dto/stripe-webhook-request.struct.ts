import {
  IsNotEmpty,
  IsObject,
  IsString,
} from 'class-validator';

export class StripeWebhookRequest {

  @IsObject()
  payload!: Record<string, unknown>;

  @IsString()
  @IsNotEmpty()
  stripeSignature!: string;


}
