
import { PartialType } from '@nestjs/mapped-types';
import { CreateUserPreferencesDto } from './create-user-preferences.dto';

export class UpdateUserPreferencesDto extends PartialType(CreateUserPreferencesDto) {}
