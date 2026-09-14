import {
  Controller,
  Delete,
  Get,
  Patch,
  Post,
  Put,
  Param,
  Query,
  DefaultValuePipe,
  ParseIntPipe,
  Body,
  Req,
  HttpCode,
  HttpStatus,
  ParseUUIDPipe,
  UseGuards,
} from '@nestjs/common';
import type { Request } from 'express';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { InternalGuard } from '../auth/internal.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { InjectRepository } from '@mikro-orm/nestjs';
import { EntityRepository } from '@mikro-orm/core';
import { UserService } from '../services/user.service';
import { UserSessionService } from '../services/user_session.service';
import { ChangePasswordRequest } from '../dto/change-password-request.struct';
import { CreateUserDto } from '../dto/create-user.dto';
import { ForgotPasswordRequest } from '../dto/forgot-password-request.struct';
import { LoginRequest } from '../dto/login-request.struct';
import { LoginResponse } from '../dto/login-response.struct';
import { LogoutRequest } from '../dto/logout-request.struct';
import { RegisterRequest } from '../dto/register-request.struct';
import { ResetPasswordRequest } from '../dto/reset-password-request.struct';
import { SessionValidationResponse } from '../dto/session-validation-response.struct';
import { UpdateProfileRequest } from '../dto/update-profile-request.struct';
import { UpdateUserDto } from '../dto/update-user.dto';
import { UpdateUserStatusRequest } from '../dto/update-user-status-request.struct';
import { UserRole } from '../enums/user-role.enum';
import { UserStatus } from '../enums/user-status.enum';
import { ValidateSessionRequest } from '../dto/validate-session-request.struct';
import { VerifyEmailRequest } from '../dto/verify-email-request.struct';
import { User } from '../ecommerce_user_service/entities/user_db/user.entity';
import { UserSession } from '../ecommerce_user_service/entities/user_db/user-session.entity';
import bcrypt from 'bcryptjs';
import validator from 'validator';
import { BadRequestException } from '@nestjs/common';
import { NotFoundException } from '@nestjs/common';
import { UnauthorizedException } from '@nestjs/common';
import { SqlEntityManager } from '@mikro-orm/postgresql';
import { _getRedis } from '../ecommerce_user_service/_cacheHelpers';
import { addDays } from 'date-fns';
import { addHours } from 'date-fns';
import { generateSessionToken } from '../functions';
import { sendPasswordResetEmail } from '../functions';
import { producerInstance as mqProducerInstance } from '../mq/producer';
import { ApiExtraModels, ApiResponse, ApiExcludeEndpoint } from '@nestjs/swagger';

@ApiExtraModels(ChangePasswordRequest, ForgotPasswordRequest, LoginRequest, LoginResponse, LogoutRequest, RegisterRequest, ResetPasswordRequest, SessionValidationResponse, UpdateProfileRequest, UpdateUserStatusRequest, ValidateSessionRequest, VerifyEmailRequest)
@UseGuards(AuthGuard)
@Controller('api/v1')
export class UserAPIController {
  constructor(
    private readonly userService: UserService,
    private readonly userSessionService: UserSessionService,
    @InjectRepository(User) private readonly userRepository: EntityRepository<User>,
    @InjectRepository(UserSession) private readonly userSessionRepository: EntityRepository<UserSession>,
  ) {}

  @Public()
  @Post('forgot-password')
  @HttpCode(HttpStatus.CREATED)
  async postForgotPassword(
    @Body() body: ForgotPasswordRequest,
  ): Promise<void> {
    let user: User | null = (await (this.userRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(User, 'e_user').select('*').where('e_user.email = ?', [body.email]).limit(1).getResultList())[0] ?? null;
    if ((user != null)) {
      user.passwordResetToken = Array.from({ length: 32 }, () => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'.charAt(Math.floor(Math.random() * 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'.length))).join('');
      user.passwordResetExpiry = addHours(new Date(), 24);
      await this.userRepository.getEntityManager().persistAndFlush(user);
      await sendPasswordResetEmail(user);
    }
  }

  @Public()
  @Post('login')
  @HttpCode(HttpStatus.CREATED)
  @ApiResponse({ status: 201, type: LoginResponse })
  async postLogin(
    @Body() body: LoginRequest,
    @Req() req: Request,
  ): Promise<LoginResponse> {
    // 'firstOrFail()' throws NotFoundException if no match
    const user = await (this.userRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(User, 'e_user').select('*').where('e_user.email = ?', [body.email]).getSingleResult();
    if (!user) {
      throw new NotFoundException("Not found");
    }
    if ((!await bcrypt.compare(body.password, user.passwordHash))) {
      throw new UnauthorizedException('Invalid credentials');
    }
    if ((!user.canLogin)) {
      throw new UnauthorizedException('Account is not active or verified');
    }
    let token: string = await generateSessionToken();
    const session = this.userSessionRepository.create({ user: user, token: token, deviceName: (req?.headers?.['user-agent'] ?? ''), ipAddress: (req?.ip ?? ''), userAgent: (req?.headers?.['user-agent'] ?? ''), expiresAt: addDays(new Date(), 30), lastActivityAt: new Date() } as never);
    await this.userSessionRepository.getEntityManager().persistAndFlush(session);
    user.lastLoginAt = new Date();
    await this.userRepository.getEntityManager().persistAndFlush(user);
    // Store session in cache for fast validation
    (await Promise.all([_getRedis().hset((String("session:") + ':' + String(token)), Object.fromEntries(Object.entries({sessionId: token, userId: user.id, lastActivity: new Date()}).map(([k, v]) => [String(k), JSON.stringify(v)]))), _getRedis().expire((String("session:") + ':' + String(token)), 2592000)]))[0];
    if (mqProducerInstance !== null) {
      await mqProducerInstance.publishUserLoggedIn({ userId: user.id, loginAt: new Date(), ipAddress: (req?.ip ?? '') });
    }
    return Object.assign(new LoginResponse(), { user: user, token: token, expiresAt: session.expiresAt });
  }

  @Post('logout')
  @HttpCode(HttpStatus.CREATED)
  async postLogout(
    @Body() body: LogoutRequest,
    @Req() req: Request,
  ): Promise<void> {
    let token: string = (req as any).user?.token;
    let session: UserSession | null = (await (this.userSessionRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(UserSession, 'e_user_session').select('*').where('e_user_session.token = ?', [token]).limit(1).getResultList())[0] ?? null;
    if ((session != null)) {
      await this.userSessionRepository.getEntityManager().removeAndFlush(session);
    }
    await _getRedis().del((String("session:") + ':' + String(token)));
  }

  @Get('me')
  async getMe(
    @Req() req: Request,
  ): Promise<User> {
    return ((u) => (u == null ? u : { ...u, id: u.id ?? u.sub }))((req as any).user);
  }

  @Patch('me')
  async putMe(
    @Body() body: UpdateProfileRequest,
    @Req() req: Request,
  ): Promise<User> {
    let user: User = ((u) => (u == null ? u : { ...u, id: u.id ?? u.sub }))((req as any).user);
    if ((body.firstName != null)) {
      user.firstName = body.firstName;
    }
    if ((body.lastName != null)) {
      user.lastName = body.lastName;
    }
    if ((body.phoneNumber != null)) {
      user.phoneNumber = body.phoneNumber;
    }
    if ((body.shippingAddress != null)) {
      user.shippingAddress = body.shippingAddress;
    }
    if ((body.billingAddress != null)) {
      user.billingAddress = body.billingAddress;
    }
    await this.userRepository.getEntityManager().persistAndFlush(user);
    return user;
  }

  @Put('me/password')
  async putMePassword(
    @Body() body: ChangePasswordRequest,
    @Req() req: Request,
  ): Promise<void> {
    let user: User = ((u) => (u == null ? u : { ...u, id: u.id ?? u.sub }))((req as any).user);
    if ((!await bcrypt.compare(body.currentPassword, user.passwordHash))) {
      throw new BadRequestException('Current password is incorrect');
    }
    user.passwordHash = await bcrypt.hash(body.newPassword, 10);
    await this.userRepository.getEntityManager().persistAndFlush(user);
  }

  @Public()
  @Post('register')
  @HttpCode(HttpStatus.CREATED)
  async postRegister(
    @Body() body: RegisterRequest,
  ): Promise<User> {
    if ((!validator.isEmail(body.email))) {
      throw new BadRequestException('Invalid email format');
    }
    if ((body.password.length < 8)) {
      throw new BadRequestException('Password must be at least 8 characters');
    }
    if ((((!/[a-z]/.test(body.password)) || (!/[A-Z]/.test(body.password))) || (!/\d/.test(body.password)))) {
      throw new BadRequestException('Password must contain lowercase, uppercase, and numbers');
    }
    let existing: User | null = (await (this.userRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(User, 'e_user').select('*').where('e_user.email = ?', [body.email]).limit(1).getResultList())[0] ?? null;
    if ((existing != null)) {
      throw new BadRequestException('Email already registered');
    }
    const user = this.userRepository.create({ email: body.email, passwordHash: await bcrypt.hash(body.password, 10), firstName: body.firstName, lastName: body.lastName, role: UserRole.Customer, status: UserStatus.Pending, emailVerificationToken: Array.from({ length: 32 }, () => 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'.charAt(Math.floor(Math.random() * 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'.length))).join('') } as never);
    await this.userRepository.getEntityManager().persistAndFlush(user);
    return user;
  }

  @Public()
  @Post('reset-password')
  @HttpCode(HttpStatus.CREATED)
  async postResetPassword(
    @Body() body: ResetPasswordRequest,
  ): Promise<User> {
    const user = await (this.userRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(User, 'e_user').select('*').where('e_user.password_reset_token = ?', [body.token]).getSingleResult();
    if (!user) {
      throw new NotFoundException("Not found");
    }
    if (((user.passwordResetExpiry == null) || (new Date() > user.passwordResetExpiry))) {
      throw new BadRequestException('Password reset token has expired');
    }
    user.passwordHash = await bcrypt.hash(body.newPassword, 10);
    user.passwordResetToken = null;
    user.passwordResetExpiry = null;
    await this.userRepository.getEntityManager().persistAndFlush(user);
    return user;
  }

  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Post('service/validate-session')
  @HttpCode(HttpStatus.CREATED)
  @ApiResponse({ status: 201, type: SessionValidationResponse })
  async postServiceValidateSession(
    @Body() body: ValidateSessionRequest,
  ): Promise<SessionValidationResponse> {
    let session: UserSession | null = (await (this.userSessionRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(UserSession, 'e_user_session').select('*').where('e_user_session.token = ?', [body.token]).limit(1).getResultList())[0] ?? null;
    if (((session == null) || session.isExpired)) {
      return Object.assign(new SessionValidationResponse(), { valid: false, user: null });
    }
    session.lastActivityAt = new Date();
    await this.userSessionRepository.getEntityManager().persistAndFlush(session);
    return Object.assign(new SessionValidationResponse(), { valid: true, user: session.user! ?? null });
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Get('users')
  async listUsers(
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<User[]> {
    return this.userService.findAll(skip, limit);
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Post('users')
  @HttpCode(HttpStatus.CREATED)
  async createUser(
    @Body() body: CreateUserDto,
  ): Promise<User> {
    const entity = this.userRepository.create(body as never);
    await this.userRepository.getEntityManager().persistAndFlush(entity);
    await this.userRepository.getEntityManager().persistAndFlush(entity);
    return entity;
  }

  @Public()
  @Post('verify-email')
  @HttpCode(HttpStatus.CREATED)
  async postVerifyEmail(
    @Body() body: VerifyEmailRequest,
  ): Promise<User> {
    const user = await (this.userRepository.getEntityManager() as SqlEntityManager).createQueryBuilder(User, 'e_user').select('*').where('e_user.email_verification_token = ?', [body.token]).getSingleResult();
    if (!user) {
      throw new NotFoundException("Not found");
    }
    user.emailVerifiedAt = new Date();
    user.emailVerificationToken = null;
    user.status = UserStatus.Active;
    await this.userRepository.getEntityManager().persistAndFlush(user);
    return user;
  }

  @Get('users/:id/user_sessions')
  async listUserSessions(
    @Param('id', ParseUUIDPipe) id: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<UserSession[]> {
    await this.userService.findOne(id);
    return this.userSessionService.getByUser(id, skip, limit);
  }

  // @internal marks endpoints as internal-only, not exposed through the API gateway
  @Public()
  @UseGuards(InternalGuard)
  @ApiExcludeEndpoint()
  @Get('service/:id')
  async getServiceById(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<User> {
    return this.userService.findOne(id);
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Delete('users/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async deleteUser(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<void> {
    let entity: User | null = await this.userRepository.findOne({ id: id });
    if (!entity) throw new NotFoundException('entity not found');
    await this.userRepository.getEntityManager().removeAndFlush(entity);
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Get('users/:id')
  async getUser(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<User> {
    return this.userService.findOne(id);
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Patch('users/:id')
  async updateUser(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: UpdateUserDto,
  ): Promise<User> {
    let entity: User | null = await this.userRepository.findOne({ id: id });
    if (!entity) throw new NotFoundException('entity not found');
    Object.assign(entity, body);
    await this.userRepository.getEntityManager().persistAndFlush(entity);
    return entity;
  }

  @UseGuards(RolesGuard)
  @Roles('Admin')
  @Patch(':id/status')
  async putByIdStatus(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: UpdateUserStatusRequest,
  ): Promise<User> {
    const user = await this.userRepository.findOne({ id: id });
    if (!user) {
      throw new NotFoundException("Not found");
    }
    user.status = body.status;
    await this.userRepository.getEntityManager().persistAndFlush(user);
    return user;
  }

}
