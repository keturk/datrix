import {
  IsBoolean,
  IsObject,
  IsOptional,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { User } from '../ecommerce_user_service/entities/user_db/user.entity'

export class SessionValidationResponse {

  @ApiProperty()
  @IsBoolean()
  valid!: boolean;

  @ApiPropertyOptional()
  @IsOptional()
  @IsObject()
  user!: User | null;


}
