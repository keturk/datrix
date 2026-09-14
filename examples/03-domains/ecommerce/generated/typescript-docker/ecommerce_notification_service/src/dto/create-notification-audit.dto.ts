
import {
  IsDate,
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
  @IsUUID()
  orderId!: string;

  @ApiProperty()
  @IsEmail()
  recipientEmail!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  @MaxLength(64)
  orderNumber!: string;
}
