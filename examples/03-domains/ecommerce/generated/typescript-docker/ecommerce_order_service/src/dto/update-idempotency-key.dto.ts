
import { PartialType } from '@nestjs/swagger';
import { CreateIdempotencyKeyDto } from './create-idempotency-key.dto';

export class UpdateIdempotencyKeyDto extends PartialType(CreateIdempotencyKeyDto) {}
