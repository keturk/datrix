import {
  IsUUID,
} from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class UpdateShipmentRequest {

  @ApiProperty()
  @IsUUID()
  shipmentId!: string;


}
