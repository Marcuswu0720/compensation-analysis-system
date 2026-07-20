import { BadRequestException, ForbiddenException, Injectable } from '@nestjs/common';
import { ApprovalStatus, AttendanceSource, AttendanceStatus, AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateLeaveTypeDto } from './dto/create-leave-type.dto';
import { CreateLeaveApplicationDto } from './dto/create-leave-application.dto';

function eachDate(start: Date, end: Date): Date[] {
  const days: Date[] = [];
  const cur = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const last = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  while (cur <= last) {
    days.push(new Date(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return days;
}

@Injectable()
export class LeaveService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  // --- 请假类型管理（10.3，可配置枚举） ---
  createLeaveType(dto: CreateLeaveTypeDto) {
    return this.prisma.leaveTypeConfig.create({ data: dto });
  }

  findLeaveTypes(activeOnly = false) {
    return this.prisma.leaveTypeConfig.findMany({ where: activeOnly ? { isActive: true } : undefined });
  }

  setLeaveTypeActive(id: string, isActive: boolean) {
    return this.prisma.leaveTypeConfig.update({ where: { id }, data: { isActive } });
  }

  // --- 请假申请 ---
  async createApplication(userId: string, dto: CreateLeaveApplicationDto) {
    const startTime = new Date(dto.startTime);
    const endTime = new Date(dto.endTime);
    if (endTime < startTime) {
      throw new BadRequestException('结束时间不能早于开始时间');
    }
    return this.prisma.leaveApplication.create({
      data: { userId, typeId: dto.typeId, startTime, endTime, reason: dto.reason, attachmentUrl: dto.attachmentUrl },
    });
  }

  findMyApplications(userId: string) {
    return this.prisma.leaveApplication.findMany({
      where: { userId },
      include: { type: true },
      orderBy: { createdAt: 'desc' },
    });
  }

  findApplications(filters: { status?: ApprovalStatus; departmentId?: string; teamId?: string }) {
    return this.prisma.leaveApplication.findMany({
      where: {
        status: filters.status,
        user: { departmentId: filters.departmentId, teamId: filters.teamId },
      },
      include: { type: true, user: { select: { id: true, name: true, employeeNo: true, team: true } } },
      orderBy: { createdAt: 'desc' },
    });
  }

  async cancel(id: string, userId: string) {
    const app = await this.prisma.leaveApplication.findUniqueOrThrow({ where: { id } });
    if (app.userId !== userId) {
      throw new ForbiddenException('只能撤销自己的申请');
    }
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('仅待审批状态可撤销');
    }
    return this.prisma.leaveApplication.update({ where: { id }, data: { status: ApprovalStatus.CANCELLED } });
  }

  // 8.1: 审批通过后自动关联到对应日期考勤记录（不计入缺勤/迟到），与打卡模式联动
  async approve(id: string, comment: string | undefined, operatorId: string) {
    const app = await this.prisma.leaveApplication.findUniqueOrThrow({ where: { id } });
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('该申请已被处理');
    }
    const updated = await this.prisma.leaveApplication.update({
      where: { id },
      data: { status: ApprovalStatus.APPROVED, approverId: operatorId, approveComment: comment },
    });

    for (const day of eachDate(app.startTime, app.endTime)) {
      await this.prisma.attendanceRecord.upsert({
        where: { userId_date: { userId: app.userId, date: day } },
        create: {
          userId: app.userId,
          date: day,
          status: AttendanceStatus.LEAVE,
          source: AttendanceSource.LEAVE_AUTO,
          remark: `请假自动标记（申请单 ${app.id}）`,
        },
        update: {
          status: AttendanceStatus.LEAVE,
          source: AttendanceSource.LEAVE_AUTO,
          remark: `请假自动标记（申请单 ${app.id}）`,
        },
      });
    }

    await this.audit.log({
      entityType: 'LEAVE_APPLICATION',
      entityId: id,
      action: AuditAction.APPROVE,
      operatorId,
      detail: { comment },
    });

    return updated;
  }

  async reject(id: string, comment: string | undefined, operatorId: string) {
    const app = await this.prisma.leaveApplication.findUniqueOrThrow({ where: { id } });
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('该申请已被处理');
    }
    const updated = await this.prisma.leaveApplication.update({
      where: { id },
      data: { status: ApprovalStatus.REJECTED, approverId: operatorId, approveComment: comment },
    });
    await this.audit.log({
      entityType: 'LEAVE_APPLICATION',
      entityId: id,
      action: AuditAction.REJECT,
      operatorId,
      detail: { comment },
    });
    return updated;
  }
}
