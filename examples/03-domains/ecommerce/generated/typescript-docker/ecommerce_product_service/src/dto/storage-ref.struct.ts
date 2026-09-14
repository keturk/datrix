import {
  IsInt,
  IsNotEmpty,
  IsOptional,
  IsString,
} from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class StorageRef {

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  folder!: string;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  key!: string;

  @ApiProperty()
  @IsInt()
  size!: number;

  @ApiProperty()
  @IsString()
  @IsNotEmpty()
  contentType!: string;

  @ApiPropertyOptional()
  @IsOptional()
  @IsString()
  checksum!: string | null;


}
