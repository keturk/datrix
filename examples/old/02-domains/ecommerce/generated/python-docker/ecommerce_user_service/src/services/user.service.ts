import { Injectable, NotFoundException, Logger, ConflictException, BadRequestException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import validator from 'validator';
import { UserRegisteredEvent } from '../events/user-registered.event';
import { UserRole } from '../enums/user-role.enum'
import { UserStatus } from '../enums/user-status.enum'
import { UserStatusChangedEvent } from '../events/user-status-changed.event';
import { UserVerifiedEvent } from '../events/user-verified.event';
import { _emailSend, _emailSendTemplate, _emailSendBulk } from '../ecommerce_user_service/_emailHelpers';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { User } from '../entities/user.entity';
import { CreateUserDto } from '../dto/create-user.dto';
import { UpdateUserDto } from '../dto/update-user.dto';
import { UserSession } from '../entities/user-session.entity';

@Injectable()
export class UserService {
  private readonly logger = new Logger(UserService.name);

  constructor(
    @InjectRepository(User)
    private readonly userRepository: Repository<User>,
    private readonly dataSource: DataSource,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(): Promise<User[]> {
    this.logger.log('Finding all User');
    return this.userRepository.find();
  }

  async findOne(id: string): Promise<User> {
    const entity = await this.userRepository.findOne({ where: { id } as any });
    if (!entity) {
      throw new NotFoundException(`User with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateUserDto): Promise<User> {
    const entity = this.userRepository.create(dto);
    this._validate(entity);
    const saved = await this.userRepository.save(entity);
this.eventEmitter.emit('UserRegistered', new UserRegisteredEvent({ userId: saved.id, email: saved.email, fullName: saved.fullName }));
await _emailSend({to: saved.email, subject: 'Verify your email', template: 'emailVerification', data: {token: saved.emailVerificationToken, fullName: saved.fullName}});
    return saved;
  }

  async update(id: string, dto: UpdateUserDto): Promise<User> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
entity.updatedAt = new Date();
    Object.assign(entity, dto);
    this._validate(entity);
    const updated = await this.userRepository.save(entity);
if (this._fieldChanged(updated, "status", oldValues)) {
  this.eventEmitter.emit('UserStatusChanged', new UserStatusChangedEvent({ userId: updated.id, oldStatus: this._fieldOldValue(updated, "status", oldValues) as UserStatus, newStatus: updated.status }));
  if (((updated.status === UserStatus.Active) && updated.isVerified)) {
    this.eventEmitter.emit('UserVerified', new UserVerifiedEvent({ userId: updated.id, email: updated.email }));
  }
}
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const userSessionCount = await this.dataSource
      .getRepository(UserSession)
      .count({ where: { userId: id } as any });
    if (userSessionCount > 0) {
      throw new ConflictException(
        `Cannot delete User '${id}': ` +
        `${ userSessionCount } sessions still reference it. ` +
        `Delete or reassign UserSession records first.`,
      );
    }
    await this.userRepository.remove(entity);
  }

  private _fieldChanged(
    current: User,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): boolean {
    if (snapshot === undefined) {
      return false;
    }
    const cur = current as unknown as Record<string, unknown>;
    return snapshot[fieldName] !== cur[fieldName];
  }

  private _fieldOldValue(
    current: User,
    fieldName: string,
    snapshot: Record<string, unknown> | undefined,
  ): unknown {
    if (snapshot === undefined) {
      return undefined;
    }
    return snapshot[fieldName];
  }


  private _validate(entity: User): void {
    const errors: string[] = [];
    if (((!validator.isEmail(entity.email)))) {
      errors.push('Invalid email format');
    }
    if ((entity.phoneNumber !== undefined && entity.phoneNumber !== null) && (((entity.phoneNumber != null) && (!validator.isMobilePhone(entity.phoneNumber))))) {
      errors.push('Invalid phone number');
    }
    if ((((entity.status === UserStatus.Active) && (!entity.isVerified)))) {
      errors.push('Cannot activate unverified user');
    }
    if (errors.length > 0) {
      throw new BadRequestException(errors.join('; '));
    }
  }

  async getByEmail(email: string): Promise<User> {
    const entity = await this.userRepository.findOne({ where: { email } as any });
    if (!entity) {
      throw new NotFoundException(`User with email ${ email } not found`);
    }
    return entity;
  }
  async findByStatusAndRole(status: UserStatus, role: UserRole, skip = 0, take = 100): Promise<User[]> {
    return this.userRepository.find({
      where: { status, role } as any,
      skip,
      take,
    });
  }

}
