import {
  IsDate,
  IsNotEmpty,
  IsObject,
  IsString,
} from 'class-validator';
import { Type } from 'class-transformer';
import { User } from '../entities/user.entity'

export class LoginResponse {

  @IsObject()
  user!: User;

  @IsString()
  @IsNotEmpty()
  token!: string;

  @IsDate()
  @Type(() => Date)
  expiresAt!: Date;


}
