import { Injectable, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService, JwtSignOptions } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { createHash, randomUUID } from 'crypto';
import { PrismaService } from '../prisma/prisma.service';
import { JwtPayload } from './auth.types';

@Injectable()
export class AuthService {
  constructor(
    private prisma: PrismaService,
    private jwtService: JwtService,
    private configService: ConfigService,
  ) {}

  async login(email: string, password: string) {
    const user = await this.prisma.user.findUnique({ where: { email } });
    if (!user || !user.isActive) {
      throw new UnauthorizedException('账号不存在或已被禁用');
    }
    const passwordMatches = await bcrypt.compare(password, user.passwordHash);
    if (!passwordMatches) {
      throw new UnauthorizedException('邮箱或密码错误');
    }
    return this.issueTokens(user.id, user.email, user.role, user.departmentId, user.teamId, {
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      employeeNo: user.employeeNo,
      departmentId: user.departmentId,
      teamId: user.teamId,
    });
  }

  async refresh(refreshToken: string) {
    let payload: JwtPayload;
    try {
      payload = this.jwtService.verify(refreshToken, {
        secret: this.configService.get<string>('JWT_REFRESH_SECRET'),
      });
    } catch {
      throw new UnauthorizedException('刷新令牌无效或已过期');
    }

    const tokenHash = this.hashToken(refreshToken);
    const stored = await this.prisma.refreshToken.findFirst({
      where: { userId: payload.sub, tokenHash, revoked: false },
    });
    if (!stored || stored.expiresAt < new Date()) {
      throw new UnauthorizedException('刷新令牌无效或已过期');
    }

    // 旋转刷新令牌：撤销旧的，签发新的
    await this.prisma.refreshToken.update({ where: { id: stored.id }, data: { revoked: true } });

    const user = await this.prisma.user.findUnique({ where: { id: payload.sub } });
    if (!user || !user.isActive) {
      throw new UnauthorizedException('账号不存在或已被禁用');
    }

    return this.issueTokens(user.id, user.email, user.role, user.departmentId, user.teamId, {
      id: user.id,
      name: user.name,
      email: user.email,
      role: user.role,
      employeeNo: user.employeeNo,
      departmentId: user.departmentId,
      teamId: user.teamId,
    });
  }

  async logout(refreshToken: string) {
    const tokenHash = this.hashToken(refreshToken);
    await this.prisma.refreshToken.updateMany({
      where: { tokenHash, revoked: false },
      data: { revoked: true },
    });
    return { success: true };
  }

  private async issueTokens(
    userId: string,
    email: string,
    role: any,
    departmentId: string | null,
    teamId: string | null,
    userSummary: Record<string, unknown>,
  ) {
    const payload: JwtPayload = { sub: userId, email, role, departmentId, teamId };

    const accessToken = this.jwtService.sign(payload, {
      secret: this.configService.get<string>('JWT_ACCESS_SECRET'),
      expiresIn: this.configService.get<string>('JWT_ACCESS_EXPIRES_IN'),
    } as JwtSignOptions);
    const refreshToken = this.jwtService.sign(
      { ...payload, jti: randomUUID() },
      {
        secret: this.configService.get<string>('JWT_REFRESH_SECRET'),
        expiresIn: this.configService.get<string>('JWT_REFRESH_EXPIRES_IN'),
      } as JwtSignOptions,
    );

    const decoded = this.jwtService.decode(refreshToken) as { exp: number };
    await this.prisma.refreshToken.create({
      data: {
        userId,
        tokenHash: this.hashToken(refreshToken),
        expiresAt: new Date(decoded.exp * 1000),
      },
    });

    return { accessToken, refreshToken, user: userSummary };
  }

  private hashToken(token: string): string {
    // refresh token 本身已是高熵随机值，用确定性哈希即可支持按值查表，无需 bcrypt 的加盐慢哈希
    return createHash('sha256').update(token).digest('hex');
  }
}
