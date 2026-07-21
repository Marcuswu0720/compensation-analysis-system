import { BadRequestException, ForbiddenException, Injectable } from '@nestjs/common';
import { ApprovalStatus, AttendanceSource, AttendanceStatus, AuditAction, Role } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateLeaveTypeDto } from './dto/create-leave-type.dto';
import { CreateLeaveApplicationDto } from './dto/create-leave-application.dto';
import { eachBusinessDate } from '../common/date-utils';

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

  // 本地HR/HRIS 自己提交、待总部特批的申请（问题反馈 2.6）
  findPendingSpecialApprovals() {
    return this.prisma.leaveApplication.findMany({
      where: { status: ApprovalStatus.PENDING, user: { role: Role.LOCAL_HR } },
      include: { type: true, user: { select: { id: true, name: true, employeeNo: true, role: true } } },
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
    // 本地HR/HRIS 没有上级，不能审批自己提交的申请，否则等于自申自批（问题反馈 2.6）
    if (app.userId === operatorId) {
      throw new ForbiddenException('不能审批自己提交的申请，请联系总部进行特批');
    }
    return this.doApprove(app, comment, operatorId);
  }

  async reject(id: string, comment: string | undefined, operatorId: string) {
    const app = await this.prisma.leaveApplication.findUniqueOrThrow({ where: { id } });
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('该申请已被处理');
    }
    if (app.userId === operatorId) {
      throw new ForbiddenException('不能审批自己提交的申请，请联系总部进行特批');
    }
    return this.doReject(app, comment, operatorId);
  }

  // 总部特批：仅用于本地HR/HRIS 自己提交、系统内无更高级审批人可用的申请单
  async specialApprove(id: string, comment: string | undefined, operatorId: string) {
    const app = await this.prisma.leaveApplication.findUniqueOrThrow({ where: { id }, include: { user: true } });
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('该申请已被处理');
    }
    if (app.user.role !== Role.LOCAL_HR) {
      throw new ForbiddenException('总部特批仅适用于本地HR/HRIS本人提交的申请');
    }
    return this.doApprove(app, comment, operatorId);
  }

  async specialReject(id: string, comment: string | undefined, operatorId: string) {
    const app = await this.prisma.leaveApplication.findUniqueOrThrow({ where: { id }, include: { user: true } });
    if (app.status !== ApprovalStatus.PENDING) {
      throw new BadRequestException('该申请已被处理');
    }
    if (app.user.role !== Role.LOCAL_HR) {
      throw new ForbiddenException('总部特批仅适用于本地HR/HRIS本人提交的申请');
    }
    return this.doReject(app, comment, operatorId);
  }

  private async doApprove(app: { id: string; userId: string; startTime: Date; endTime: Date }, comment: string | undefined, operatorId: string) {
    const updated = await this.prisma.leaveApplication.update({
      where: { id: app.id },
      data: { status: ApprovalStatus.APPROVED, approverId: operatorId, approveComment: comment },
    });

    for (const day of eachBusinessDate(app.startTime, app.endTime)) {
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
      entityId: app.id,
      action: AuditAction.APPROVE,
      operatorId,
      detail: { comment },
    });

    return updated;
  }

  private async doReject(app: { id: string }, comment: string | undefined, operatorId: string) {
    const updated = await this.prisma.leaveApplication.update({
      where: { id: app.id },
      data: { status: ApprovalStatus.REJECTED, approverId: operatorId, approveComment: comment },
    });
    await this.audit.log({
      entityType: 'LEAVE_APPLICATION',
      entityId: app.id,
      action: AuditAction.REJECT,
      operatorId,
      detail: { comment },
    });
    return updated;
  }
}
