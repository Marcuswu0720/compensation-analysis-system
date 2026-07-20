import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import { AttendanceMode, AttendanceSource, AttendanceStatus } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { OfficesService } from '../offices/offices.service';

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function combineDateAndTime(date: Date, hhmm: string): Date {
  const [h, m] = hhmm.split(':').map(Number);
  const d = new Date(date);
  d.setHours(h, m, 0, 0);
  return d;
}

@Injectable()
export class AttendanceService {
  constructor(
    private prisma: PrismaService,
    private offices: OfficesService,
  ) {}

  private async resolveEffectiveRule(teamId: string | null) {
    if (!teamId) {
      return {
        requiresClockIn: true,
        requiresClockOut: true,
        requiresPhoto: false,
        requiresBusinessMetric: false,
        businessMetricThreshold: null as number | null,
        officeAssignmentMode: 'NONE' as const,
      };
    }
    const [modeConfig, ruleTemplate] = await Promise.all([
      this.prisma.teamAttendanceModeConfig.findUnique({ where: { teamId } }),
      this.prisma.teamAttendanceRuleTemplate.findUnique({ where: { teamId } }),
    ]);
    const mode = modeConfig?.mode ?? AttendanceMode.OFFICE;
    if (ruleTemplate) {
      return {
        mode,
        requiresClockIn: ruleTemplate.requiresClockIn,
        requiresClockOut: ruleTemplate.requiresClockOut,
        requiresPhoto: ruleTemplate.requiresPhoto,
        requiresBusinessMetric: ruleTemplate.requiresBusinessMetric,
        businessMetricThreshold: ruleTemplate.businessMetricThreshold,
        officeAssignmentMode: ruleTemplate.officeAssignmentMode,
      };
    }
    return {
      mode,
      requiresClockIn: mode !== AttendanceMode.LOCATION,
      requiresClockOut: mode !== AttendanceMode.LOCATION,
      requiresPhoto: mode === AttendanceMode.LOCATION,
      requiresBusinessMetric: false,
      businessMetricThreshold: null as number | null,
      officeAssignmentMode: 'NONE' as const,
    };
  }

  async clockIn(userId: string, dto: { lat?: number; lng?: number }) {
    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: userId } });
    const rule = await this.resolveEffectiveRule(user.teamId);

    if (!rule.requiresClockIn) {
      throw new BadRequestException('该团队/岗位打卡方式非标准打卡，请使用定位打卡（拍照/GPS）接口');
    }

    const now = new Date();
    const today = startOfDay(now);

    let status: AttendanceStatus = AttendanceStatus.NORMAL;
    let lateMinutes = 0;
    let source: AttendanceSource = AttendanceSource.MANUAL;
    let scheduleAssignmentId: string | undefined;

    if (rule.mode === AttendanceMode.SHIFT) {
      const assignment = await this.prisma.scheduleAssignment.findFirst({
        where: { userId, date: today },
        include: { shift: true },
        orderBy: { createdAt: 'desc' },
      });
      if (!assignment) {
        throw new BadRequestException('今日无排班记录，无法打卡，请联系本地HR确认排班');
      }
      scheduleAssignmentId = assignment.id;
      const expectedStart = combineDateAndTime(today, assignment.shift.startTime);
      lateMinutes = Math.max(0, Math.round((now.getTime() - expectedStart.getTime()) / 60000));
      status = lateMinutes > 0 ? AttendanceStatus.LATE : AttendanceStatus.NORMAL;
      source = AttendanceSource.SHIFT_CLOCK;
    } else if (rule.officeAssignmentMode === 'NEAREST_AUTO') {
      if (dto.lat === undefined || dto.lng === undefined) {
        throw new BadRequestException('该岗位需上传定位以自动分配最近办公室');
      }
      const nearest = await this.offices.findNearest(dto.lat, dto.lng);
      if (!nearest) {
        throw new BadRequestException('未找到可用办公室，请联系本地HR');
      }
      status = AttendanceStatus.NORMAL;
      source = AttendanceSource.OFFICE_CLOCK;
    } else {
      const officeRule = user.teamId
        ? await this.prisma.officeAttendanceRule.findUnique({ where: { teamId: user.teamId } })
        : null;
      if (officeRule) {
        const graceStart = combineDateAndTime(today, officeRule.startTime);
        graceStart.setMinutes(graceStart.getMinutes() + officeRule.lateGraceMinutes);
        lateMinutes = Math.max(0, Math.round((now.getTime() - graceStart.getTime()) / 60000));
        status = lateMinutes > 0 ? AttendanceStatus.LATE : AttendanceStatus.NORMAL;
      }
      source = AttendanceSource.OFFICE_CLOCK;
    }

    const existing = await this.prisma.attendanceRecord.findUnique({ where: { userId_date: { userId, date: today } } });
    if (existing?.clockInAt) {
      throw new BadRequestException('今日已打过上班卡');
    }

    return this.prisma.attendanceRecord.upsert({
      where: { userId_date: { userId, date: today } },
      create: {
        userId,
        date: today,
        clockInAt: now,
        status,
        source,
        lateMinutes,
        scheduleAssignmentId,
      },
      update: {
        clockInAt: now,
        status,
        source,
        lateMinutes,
        scheduleAssignmentId,
      },
    });
  }

  async clockOut(userId: string, _dto: { lat?: number; lng?: number }) {
    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: userId } });
    const rule = await this.resolveEffectiveRule(user.teamId);

    if (!rule.requiresClockOut) {
      throw new BadRequestException('该团队/岗位下班无需打卡');
    }

    const now = new Date();
    const today = startOfDay(now);
    const record = await this.prisma.attendanceRecord.findUnique({ where: { userId_date: { userId, date: today } } });
    if (!record || !record.clockInAt) {
      throw new BadRequestException('请先完成上班打卡');
    }
    if (record.clockOutAt) {
      throw new BadRequestException('今日已打过下班卡');
    }

    let earlyMinutes = 0;
    let status = record.status;

    if (rule.mode === AttendanceMode.SHIFT && record.scheduleAssignmentId) {
      const assignment = await this.prisma.scheduleAssignment.findUniqueOrThrow({
        where: { id: record.scheduleAssignmentId },
        include: { shift: true },
      });
      const expectedEnd = combineDateAndTime(today, assignment.shift.endTime);
      earlyMinutes = Math.max(0, Math.round((expectedEnd.getTime() - now.getTime()) / 60000));
    } else if (user.teamId) {
      const officeRule = await this.prisma.officeAttendanceRule.findUnique({ where: { teamId: user.teamId } });
      if (officeRule) {
        const graceEnd = combineDateAndTime(today, officeRule.endTime);
        graceEnd.setMinutes(graceEnd.getMinutes() - officeRule.earlyGraceMinutes);
        earlyMinutes = Math.max(0, Math.round((graceEnd.getTime() - now.getTime()) / 60000));
      }
    }

    if (earlyMinutes > 0 && status === AttendanceStatus.NORMAL) {
      status = AttendanceStatus.EARLY_LEAVE;
    }

    return this.prisma.attendanceRecord.update({
      where: { id: record.id },
      data: { clockOutAt: now, earlyMinutes, status },
    });
  }

  async findMyCalendar(userId: string, month?: string) {
    const { start, end } = monthRange(month);
    return this.prisma.attendanceRecord.findMany({
      where: { userId, date: { gte: start, lt: end } },
      orderBy: { date: 'asc' },
    });
  }

  async findAll(filters: { userId?: string; departmentId?: string; teamId?: string; month?: string }) {
    const { start, end } = monthRange(filters.month);
    return this.prisma.attendanceRecord.findMany({
      where: {
        userId: filters.userId,
        date: { gte: start, lt: end },
        user: {
          departmentId: filters.departmentId,
          teamId: filters.teamId,
        },
      },
      include: { user: { select: { id: true, name: true, employeeNo: true, department: true, team: true } } },
      orderBy: { date: 'desc' },
    });
  }

  async findToday(userId: string) {
    const today = startOfDay(new Date());
    const record = await this.prisma.attendanceRecord.findUnique({ where: { userId_date: { userId, date: today } } });
    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: userId } });
    const rule = await this.resolveEffectiveRule(user.teamId);
    return { record, effectiveRule: rule };
  }
}

function monthRange(month?: string): { start: Date; end: Date } {
  const now = month ? new Date(`${month}-01T00:00:00`) : new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  return { start, end };
}
