import {
  IsOptional,
  IsString,
} from 'class-validator';

export class CancelOrderRequest {

  @IsOptional()
  @IsString()
  reason?: string | null;


}
