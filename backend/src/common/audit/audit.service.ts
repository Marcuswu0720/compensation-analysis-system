import { Injectable } from '@nestjs/common';
import { AuditAction, Prisma } from '@prisma/client';
import { PrismaService } from '../../prisma/prisma.service';

interface LogParams {
  entityType: string;
  entityId: string;
  action: AuditAction;
  operatorId: string;
  detail?: Prisma.InputJsonValue;
}

@Injectable()
export class AuditService {
  constructor(private prisma: PrismaService) {}

  async log(params: LogParams) {
    return this.prisma.auditLog.create({
      data: {
        entityType: params.entityType,
        entityId: params.entityId,
        action: params.action,
        operatorId: params.operatorId,
        detail: params.detail,
      },
    });
  }

  async findAll(filters: { entityType?: string; entityId?: string; operatorId?: string }) {
    return this.prisma.auditLog.findMany({
      where: {
        entityType: filters.entityType,
        entityId: filters.entityId,
        operatorId: filters.operatorId,
      },
      include: { operator: { select: { id: true, name: true, email: true } } },
      orderBy: { operatedAt: 'desc' },
      take: 200,
    });
  }
}
