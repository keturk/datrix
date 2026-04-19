import {
  IsNotEmpty,
  IsString,
} from 'class-validator';

export class ValidateSessionRequest {

  @IsString()
  @IsNotEmpty()
  token!: string;


}
