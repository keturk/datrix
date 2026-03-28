import {
  IsBoolean,
  IsOptional,
  IsString,
} from 'class-validator';

export class RefundResult {

  @IsBoolean()
  success!: boolean;

  @IsOptional()
  @IsString()
  refundTransactionId?: string | null;

  @IsOptional()
  @IsString()
  error?: string | null;


}
