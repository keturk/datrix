import {
  IsBoolean,
  IsObject,
  IsOptional,
} from 'class-validator';
import { User } from '../entities/user.entity'

export class SessionValidationResponse {

  @IsBoolean()
  valid!: boolean;

  @IsOptional()
  @IsObject()
  user?: User | null;


}
