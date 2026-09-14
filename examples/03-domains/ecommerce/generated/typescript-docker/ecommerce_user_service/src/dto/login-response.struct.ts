import {
  IsDate,
  IsNotEmpty,
  IsObject,
  IsString,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { User } from '../ecommerce_user_service/entities/user_db/user.entity'

export class LoginResponse {

  // 'userDb.User' references an entity type from this service's database
  @ApiProperty()
  @IsObject()
  user!: User;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  token!: string;

  @ApiProperty()
  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;


}
