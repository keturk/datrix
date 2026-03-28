import {
  IsBoolean,
  IsOptional,
} from 'class-validator';

export class LogoutRequest {

  @IsOptional()
  @IsBoolean()
  revokeAll?: boolean | null;


}
