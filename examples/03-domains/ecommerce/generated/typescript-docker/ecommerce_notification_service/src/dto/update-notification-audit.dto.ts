
import { PartialType } from '@nestjs/swagger';
import { CreateNotificationAuditDto } from './create-notification-audit.dto';

export class UpdateNotificationAuditDto extends PartialType(CreateNotificationAuditDto) {}
