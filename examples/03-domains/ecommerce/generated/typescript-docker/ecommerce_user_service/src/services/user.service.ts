import { Injectable, NotFoundException, Logger, ConflictException, BadRequestException } from '@nestjs/common';
import { EventEmitter2 } from '@nestjs/event-emitter';
import validator from 'validator';
import { UserRole } from '../enums/user-role.enum'
import { UserStatus } from '../enums/user-status.enum'
import { userDbUserAfterCreate } from '../hooks/user-db-user-after-create.hook';
import { userDbUserAfterUpdate } from '../hooks/user-db-user-after-update.hook';
import { userDbUserBeforeUpdate } from '../hooks/user-db-user-before-update.hook';
import { EntityManager } from '@mikro-orm/core';
import { User } from '../ecommerce_user_service/entities/user_db/user.entity';
import { CreateUserDto } from '../dto/create-user.dto';
import { UpdateUserDto } from '../dto/update-user.dto';
import { UserSession } from '../ecommerce_user_service/entities/user_db/user-session.entity';

@Injectable()
export class UserService {
  private readonly logger = new Logger(UserService.name);

  constructor(
    private readonly em: EntityManager,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  async findAll(skip: number | null = 0, take: number | null = 100): Promise<User[]> {
    this.logger.log('Finding all User');
    return this.em.find(
      User,
      {} as never,
      { limit: take ?? 100, offset: skip ?? 0 },
    );
  }

  async findOne(id: string): Promise<User> {
    const entity = await this.em.findOne(User, { id } as never);
    if (!entity) {
      throw new NotFoundException(`User with id ${id} not found`);
    }
    return entity;
  }

  async create(dto: CreateUserDto): Promise<User> {
    const entity = this.em.create(User, dto as never);
    this._validate(entity);
    await this.em.persistAndFlush(entity);
    const saved = entity;
    await userDbUserAfterCreate(saved, this.em!);
    return saved;
  }

  async update(id: string, dto: UpdateUserDto): Promise<User> {
    const entity = await this.findOne(id);
    const oldValues: Record<string, unknown> = { ...entity };
    await userDbUserBeforeUpdate(entity, this.em, oldValues);
    this.em.assign(entity, dto as never);
    this._validate(entity);
    await this.em.flush();
    const updated = entity;
    await userDbUserAfterUpdate(updated, this.em, oldValues);
    return updated;
  }

  async remove(id: string): Promise<void> {
    const entity = await this.findOne(id);
    const userSessionCount = await this.em.count(UserSession, {
      user: id,
    } as never);
    if (userSessionCount > 0) {
      throw new ConflictException(
        `Cannot delete User '${id}': ` +
        `${ userSessionCount } sessions still reference it. ` +
        `Delete or reassign UserSession records first.`,
      );
    }
    await this.em.removeAndFlush(entity);
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
    const entity = await this.em.findOne(User, {
      email
    } as never);
    if (!entity) {
      throw new NotFoundException(`User with email ${ email } not found`);
    }
    return entity;
  }
  async findByStatusAndRole(status: UserStatus, role: UserRole, skip = 0, take = 100): Promise<User[]> {
    return this.em.find(
      User,
      { status, role } as never,
      { limit: take, offset: skip },
    );
  }

}
