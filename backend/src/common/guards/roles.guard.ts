import { ExecutionContext, ForbiddenException, Injectable } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Role } from '@prisma/client';
import { IS_PUBLIC_KEY } from '../decorators/public.decorator';
import { ROLES_KEY } from '../decorators/roles.decorator';
import { ALLOW_HQ_WRITE_KEY } from '../decorators/allow-hq-write.decorator';

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

@Injectable()
export class RolesGuard {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (isPublic) {
      return true;
    }

    const request = context.switchToHttp().getRequest();
    const user = request.user;

    // 强约束（需求文档 2.2 节）：总部账号在网关层被拒绝一切写操作，
    // 无论前端是否隐藏了对应按钮。
    if (user?.role === Role.HQ && !SAFE_METHODS.has(request.method)) {
      const allowHqWrite = this.reflector.getAllAndOverride<boolean>(ALLOW_HQ_WRITE_KEY, [
        context.getHandler(),
        context.getClass(),
      ]);
      if (!allowHqWrite) {
        throw new ForbiddenException('总部账号仅拥有只读权限');
      }
    }

    const requiredRoles = this.reflector.getAllAndOverride<Role[]>(ROLES_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (!requiredRoles || requiredRoles.length === 0) {
      return true;
    }

    if (!user || !requiredRoles.includes(user.role)) {
      throw new ForbiddenException('权限不足');
    }
    return true;
  }
}
