import {
  IsNotEmpty,
  IsString,
} from 'class-validator';

export class ChangePasswordRequest {

  @IsString()
  @IsNotEmpty()
  currentPassword!: string;

  @IsString()
  @IsNotEmpty()
  newPassword!: string;


}
