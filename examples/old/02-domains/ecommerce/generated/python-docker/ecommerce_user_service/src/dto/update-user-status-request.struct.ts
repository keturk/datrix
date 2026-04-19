import {
  IsEnum,
} from 'class-validator';
import { UserStatus } from '../enums/user-status.enum'

export class UpdateUserStatusRequest {

  @IsEnum(UserStatus)
  status!: UserStatus;


}
