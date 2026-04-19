import {
  IsUUID,
} from 'class-validator';

export class UpdateShipmentRequest {

  @IsUUID()
  shipmentId!: string;


}
