import { BadRequestException, ForbiddenException, Injectable } from '@nestjs/common';
import { ApprovalStatus, AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateOvertimeDto } from './dto/create-overtime.dto';

@Injectable()
export class OvertimeService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  createApplication(userId: string, dto: CreateOvertimeDto) {
    return this.prisma.overtimeApplication.create({
      data: { userId, date: new Date(dto.date), hours: dto.hours, reason: dto.reason },
    });
  }

  findMyApplications(userId: string) {
    return this.prisma.overtimeApplication.findMany({ where: { userId }, orderBy: { createdAt: 'desc' } });
  }

  findApplications(filters: { status?: ApprovalStatus; departmentId?: string; teamId?: string }) {
    return this.prisma.overtimeApplication.findMany({
      where: { status: filters.status, user: { departmentId: filters.departmentId, teamId: filters.teamId } },
      include: { user: { select: { id: true, name: true, employeeNo: true, team: true } } },
      orderBy: { createdAt: 'desc' },
    });
  }

  async cancel(id: string, userId: string) {
    const app = await this.prisma.overtimeApplication.findUniqueOrThrow({ where: { id } });
    if (app.userId !== userId) {
      throw new ForbiddenException('只能撤销自己的申请');
    }
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('仅待审批状态可撤销');
    }
    return this.prisma.overtimeApplication.update({ where: { id }, data: { status: ApprovalStatus.CANCELLED } });
  }

  async approve(id: string, comment: string | undefined, operatorId: string) {
    const app = await this.prisma.overtimeApplication.findUniqueOrThrow({ where: { id } });
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('该申请已被处理');
    }
    const updated = await this.prisma.overtimeApplication.update({
      where: { id },
      data: { status: ApprovalStatus.APPROVED, approverId: operatorId, approveComment: comment },
    });
    await this.audit.log({ entityType: 'OVERTIME_APPLICATION', entityId: id, action: AuditAction.APPROVE, operatorId, detail: { comment } });
    return updated;
  }

  async reject(id: string, comment: string | undefined, operatorId: string) {
    const app = await this.prisma.overtimeApplication.findUniqueOrThrow({ where: { id } });
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('该申请已被处理');
    }
    const updated = await this.prisma.overtimeApplication.update({
      where: { id },
      data: { status: ApprovalStatus.REJECTED, approverId: operatorId, approveComment: comment },
    });
    await this.audit.log({ entityType: 'OVERTIME_APPLICATION', entityId: id, action: AuditAction.REJECT, operatorId, detail: { comment } });
    return updated;
  }
}
