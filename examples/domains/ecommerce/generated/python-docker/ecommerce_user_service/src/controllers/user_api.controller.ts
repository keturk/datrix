import {
  Controller,
  Delete,
  Get,
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
import { Request } from 'express';
import { EventEmitter2 } from '@nestjs/event-emitter';
import { AuthGuard } from '../auth/auth.guard';
import { Public } from '../auth/public.decorator';
import { InternalGuard } from '../auth/internal.guard';
import { RolesGuard } from '../auth/roles.guard';
import { Roles } from '../auth/roles.decorator';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { UserService } from '../services/user.service';
import { UserSessionService } from '../services/user_session.service';
import { ChangePasswordRequest } from '../dto/change-password-request.struct';
import { ForgotPasswordRequest } from '../dto/forgot-password-request.struct';
import { LoginRequest } from '../dto/login-request.struct';
import { LoginResponse } from '../dto/login-response.struct';
import { LogoutRequest } from '../dto/logout-request.struct';
import { NotFoundException } from '@nestjs/common';
import { RegisterRequest } from '../dto/register-request.struct';
import { ResetPasswordRequest } from '../dto/reset-password-request.struct';
import { SessionValidationResponse } from '../dto/session-validation-response.struct';
import { UpdateProfileRequest } from '../dto/update-profile-request.struct';
import { UpdateUserStatusRequest } from '../dto/update-user-status-request.struct';
import { UserLoggedInEvent } from '../events/user-logged-in.event';
import { UserRole } from '../enums/user-role.enum';
import { UserStatus } from '../enums/user-status.enum';
import { ValidateSessionRequest } from '../dto/validate-session-request.struct';
import { VerifyEmailRequest } from '../dto/verify-email-request.struct';
import { _getRedis } from '../ecommerce_user_service/_cacheHelpers';
import { addDays } from 'date-fns';
import { addHours } from 'date-fns';
import { generateSessionToken } from 'ecommerce-user-service/auth';
import { generateToken } from 'ecommerce-user-service/auth';
import { hashPassword } from 'ecommerce-user-service/auth';
import { sendPasswordResetEmail } from 'ecommerce-user-service/functions';
import { verifyPassword } from 'ecommerce-user-service/auth';
import { User } from '../entities/user.entity';
import { UserSession } from '../entities/user-session.entity';
import validator from 'validator';
import { BadRequestException, ForbiddenException, UnauthorizedException } from '@nestjs/common';

@UseGuards(AuthGuard)
@Controller('api/v1')
export class UserAPIController {
  constructor(
    private readonly userService: UserService,
    private readonly userSessionService: UserSessionService,
    @InjectRepository(User) private readonly userRepository: Repository<User>,
    @InjectRepository(UserSession) private readonly userSessionRepository: Repository<UserSession>,
    private readonly eventEmitter: EventEmitter2,
  ) {}

  @Public()
  @Post('forgot-password')
  @HttpCode(HttpStatus.CREATED)
  async postForgotPassword(
    @Body() request: ForgotPasswordRequest,
  ): Promise<void> {
    const user: User | null = await this.userRepository.createQueryBuilder('user').where('user.email = :email', { email: request.email }).getOne();
    if ((user != null)) {
      user.passwordResetToken = generateToken();
      user.passwordResetExpiry = addHours(new Date(), 24);
      await this.userRepository.save(user);
      sendPasswordResetEmail(user);
    }
  }

  @UseGuards(InternalGuard)
  @Post('internal/validate-session')
  @HttpCode(HttpStatus.CREATED)
  async postInternalValidateSession(
    @Body() request: ValidateSessionRequest,
  ): Promise<SessionValidationResponse> {
    const session: UserSession | null = await this.userSessionRepository.createQueryBuilder('userSession').where('userSession.token = :token', { token: request.token }).getOne();
    if (((session == null) || session.isExpired)) {
      return {valid: false, user: null};
    }
    session.lastActivityAt = new Date();
    await this.userSessionRepository.save(session);
    return {valid: true, user: session.user};
  }

  @Public()
  @Post('login')
  @HttpCode(HttpStatus.CREATED)
  async postLogin(
    @Body() request: LoginRequest,
    @Req() req: Request,
  ): Promise<LoginResponse> {
    const user = await this.userRepository.createQueryBuilder('user').where('user.email = :email', { email: request.email }).getOneOrFail();
    if ((!verifyPassword(request.password, user.passwordHash))) {
      throw new UnauthorizedException('Invalid credentials');
    }
    if ((!user.canLogin)) {
      throw new UnauthorizedException('Account is not active or verified');
    }
    const token: string = generateSessionToken();
    const session = this.userSessionRepository.create({user: user, token: token, deviceName: (req?.headers?.['user-agent'] ?? ''), ipAddress: (req?.ip ?? ''), userAgent: (req?.headers?.['user-agent'] ?? ''), expiresAt: addDays(new Date(), 30), lastActivityAt: new Date()});
    await this.userSessionRepository.save(session);
    user.lastLoginAt = new Date();
    await this.userRepository.save(user);
    await _getRedis().set(`sessionCache:${token}`, JSON.stringify({sessionId: token, userId: user.id, lastActivity: new Date()}));;
    this.eventEmitter.emit('UserLoggedIn', new UserLoggedInEvent({ userId: user.id, loginAt: new Date(), ipAddress: (req?.ip ?? '') }));
    return {user: user, token: token, expiresAt: session.expiresAt};
  }

  @Post('logout')
  @HttpCode(HttpStatus.CREATED)
  async postLogout(
    @Body() request: LogoutRequest,
    @Req() req: Request,
  ): Promise<void> {
    const token: string = (req as any).user?.token;
    const session: UserSession | null = await this.userSessionRepository.createQueryBuilder('userSession').where('userSession.token = :token', { token: token }).getOne();
    if ((session != null)) {
      await this.userSessionRepository.remove(session);
    }
    await _getRedis().del(`sessionCache:${token}`);;
  }

  @Get('me')
  async getMe(
    @Req() req: Request,
  ): Promise<User> {
    return (req as any).user;
  }

  @Put('me')
  async putMe(
    @Body() request: UpdateProfileRequest,
    @Req() req: Request,
  ): Promise<User> {
    const user: User = (req as any).user;
    if ((request.firstName != null)) {
      user.firstName = request.firstName;
    }
    if ((request.lastName != null)) {
      user.lastName = request.lastName;
    }
    if ((request.phoneNumber != null)) {
      user.phoneNumber = request.phoneNumber;
    }
    if ((request.shippingAddress != null)) {
      user.shippingAddress = request.shippingAddress;
    }
    if ((request.billingAddress != null)) {
      user.billingAddress = request.billingAddress;
    }
    await this.userRepository.save(user);
    return user;
  }

  @Put('me/password')
  async putMePassword(
    @Body() request: ChangePasswordRequest,
    @Req() req: Request,
  ): Promise<void> {
    const user: User = (req as any).user;
    if ((!verifyPassword(request.currentPassword, user.passwordHash))) {
      throw new BadRequestException('Current password is incorrect');
    }
    user.passwordHash = hashPassword(request.newPassword);
    await this.userRepository.save(user);
  }

  @Public()
  @Post('register')
  @HttpCode(HttpStatus.CREATED)
  async postRegister(
    @Body() request: RegisterRequest,
  ): Promise<User> {
    if ((!validator.isEmail(request.email))) {
      throw new BadRequestException('Invalid email format');
    }
    if ((request.password.length < 8)) {
      throw new BadRequestException('Password must be at least 8 characters');
    }
    if ((((!/[a-z]/.test(request.password)) || (!/[A-Z]/.test(request.password))) || (!/\d/.test(request.password)))) {
      throw new BadRequestException('Password must contain lowercase, uppercase, and numbers');
    }
    const existing: User | null = await this.userRepository.createQueryBuilder('user').where('user.email = :email', { email: request.email }).getOne();
    if ((existing != null)) {
      throw new BadRequestException('Email already registered');
    }
    const user = this.userRepository.create({email: request.email, passwordHash: hashPassword(request.password), firstName: request.firstName, lastName: request.lastName, role: UserRole.Customer, status: UserStatus.Pending, emailVerificationToken: generateToken()});
    await this.userRepository.save(user);
    return user;
  }

  @Public()
  @Post('reset-password')
  @HttpCode(HttpStatus.CREATED)
  async postResetPassword(
    @Body() request: ResetPasswordRequest,
  ): Promise<User> {
    const user = await this.userRepository.createQueryBuilder('user').where('user.passwordResetToken = :passwordResetToken', { passwordResetToken: request.token }).getOneOrFail();
    if (((user.passwordResetExpiry == null) || (new Date() > user.passwordResetExpiry))) {
      throw new BadRequestException('Password reset token has expired');
    }
    user.passwordHash = hashPassword(request.newPassword);
    user.passwordResetToken = null;
    user.passwordResetExpiry = null;
    await this.userRepository.save(user);
    return user;
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Get('users')
  async listUsers(
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('limit', new DefaultValuePipe(20), ParseIntPipe) limit: number,
  ): Promise<User[]> {
    return this.userService.findAll();
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Post('users')
  @HttpCode(HttpStatus.CREATED)
  async createUser(
    @Body() body: User,
  ): Promise<User> {
    return this.userService.create(body);
  }

  @Public()
  @Post('verify-email')
  @HttpCode(HttpStatus.CREATED)
  async postVerifyEmail(
    @Body() request: VerifyEmailRequest,
  ): Promise<User> {
    const user = await this.userRepository.createQueryBuilder('user').where('user.emailVerificationToken = :emailVerificationToken', { emailVerificationToken: request.token }).getOneOrFail();
    user.emailVerifiedAt = new Date();
    user.emailVerificationToken = null;
    user.status = UserStatus.Active;
    await this.userRepository.save(user);
    return user;
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Put(':id/status')
  async putStatus(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() request: UpdateUserStatusRequest,
  ): Promise<User> {
    const user = await this.userRepository.findOneOrFail({ where: { id: id } });
    user.status = request.status;
    await this.userRepository.save(user);
    return user;
  }

  @UseGuards(InternalGuard)
  @Get('internal/:id')
  async getInternal(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<User> {
    return this.userService.findOne(id);
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Delete('users/:id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async deleteUser(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<void> {
    await this.userService.remove(id);
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Get('users/:id')
  async getUser(
    @Param('id', ParseUUIDPipe) id: string,
  ): Promise<User> {
    return this.userService.findOne(id);
  }

  @UseGuards(RolesGuard)
  @Roles('admin')
  @Put('users/:id')
  async updateUser(
    @Param('id', ParseUUIDPipe) id: string,
    @Body() body: User,
  ): Promise<User> {
    return this.userService.update(id, body);
  }

  @Get('users/:id/user_sessions')
  async listUserSessions(
    @Param('id', ParseUUIDPipe) id: string,
    @Query('skip', new DefaultValuePipe(0), ParseIntPipe) skip: number,
    @Query('take', new DefaultValuePipe(20), ParseIntPipe) take: number,
  ): Promise<UserSession[]> {
    await this.userService.findOne(id);
    return this.userSessionService.getByUser(id, skip, take);
  }

}
