import {
  IsNotEmpty,
  IsString,
} from 'class-validator';

export class ResetPasswordRequest {

  @IsString()
  @IsNotEmpty()
  token!: string;

  @IsString()
  @IsNotEmpty()
  newPassword!: string;


}
