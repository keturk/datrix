
import {
  IsDefined,
  IsEmail,
  IsNotEmpty,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  MaxLength,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';

export class CreateNotificationAuditDto {

  @ApiProperty()
  @IsDefined()
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsDefined()
  @IsEmail()
  recipientEmail!: string;

  @ApiProperty()
  @IsDefined()
  @IsString()
  @IsNotEmpty()
  @MaxLength(64)
  orderNumber!: string;
}
