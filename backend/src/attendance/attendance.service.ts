import { BadRequestException, Injectable } from '@nestjs/common';
import { AttendanceMode, AttendanceSource, AttendanceStatus } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { OfficesService } from '../offices/offices.service';
import { businessToday, combineBusinessDateAndTime, toBusinessDateOnly } from '../common/date-utils';

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
    const today = businessToday();

    let status: AttendanceStatus = AttendanceStatus.NORMAL;
    let lateMinutes = 0;
    let source: AttendanceSource = AttendanceSource.MANUAL;
    let scheduleAssignmentId: string | undefined;
    let matchedOfficeId: string | undefined;

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
      const expectedStart = combineBusinessDateAndTime(today, assignment.shift.startTime);
      lateMinutes = Math.max(0, Math.round((now.getTime() - expectedStart.getTime()) / 60000));
      status = lateMinutes > 0 ? AttendanceStatus.LATE : AttendanceStatus.NORMAL;
      source = AttendanceSource.SHIFT_CLOCK;
    } else {
      // 办公室打卡（含"最近办公室自动分配"变体，例如地催团队：两者共用同一套迟到判定逻辑，
      // NEAREST_AUTO 只是在此基础上额外做定位匹配，不应跳过迟到判断 —— 见问题反馈 2.1/4.1）
      if (rule.officeAssignmentMode === 'NEAREST_AUTO') {
        if (dto.lat === undefined || dto.lng === undefined) {
          throw new BadRequestException('该岗位需上传定位以自动分配最近办公室');
        }
        const nearest = await this.offices.findNearest(dto.lat, dto.lng);
        if (!nearest) {
          throw new BadRequestException('未找到可用办公室，请联系本地HR');
        }
        matchedOfficeId = nearest.office.id;
      }

      const officeRule = user.teamId
        ? await this.prisma.officeAttendanceRule.findUnique({ where: { teamId: user.teamId } })
        : null;

      if (!officeRule) {
        // 员工未配置团队，或团队未配置打卡规则：无法判定迟到/早退，明确标记而非默默算作"正常"（问题反馈 2.2）
        status = AttendanceStatus.UNCONFIGURED;
      } else {
        const graceStart = combineBusinessDateAndTime(today, officeRule.startTime);
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
        matchedOfficeId,
        clockInLat: dto.lat,
        clockInLng: dto.lng,
      },
      update: {
        clockInAt: now,
        status,
        source,
        lateMinutes,
        scheduleAssignmentId,
        matchedOfficeId,
        clockInLat: dto.lat,
        clockInLng: dto.lng,
      },
      include: { matchedOffice: true },
    });
  }

  async clockOut(userId: string, _dto: { lat?: number; lng?: number }) {
    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: userId } });
    const rule = await this.resolveEffectiveRule(user.teamId);

    if (!rule.requiresClockOut) {
      throw new BadRequestException('该团队/岗位下班无需打卡');
    }

    const now = new Date();
    const today = businessToday();
    const record = await this.prisma.attendanceRecord.findUnique({ where: { userId_date: { userId, date: today } } });
    if (!record || !record.clockInAt) {
      throw new BadRequestException('请先完成上班打卡');
    }
    if (record.clockOutAt) {
      throw new BadRequestException('今日已打过下班卡');
    }

    let earlyMinutes = 0;
    let status = record.status;
    let hasRule: boolean;

    if (rule.mode === AttendanceMode.SHIFT && record.scheduleAssignmentId) {
      const assignment = await this.prisma.scheduleAssignment.findUniqueOrThrow({
        where: { id: record.scheduleAssignmentId },
        include: { shift: true },
      });
      const expectedEnd = combineBusinessDateAndTime(today, assignment.shift.endTime);
      earlyMinutes = Math.max(0, Math.round((expectedEnd.getTime() - now.getTime()) / 60000));
      hasRule = true;
    } else if (user.teamId) {
      const officeRule = await this.prisma.officeAttendanceRule.findUnique({ where: { teamId: user.teamId } });
      if (officeRule) {
        const graceEnd = combineBusinessDateAndTime(today, officeRule.endTime);
        graceEnd.setMinutes(graceEnd.getMinutes() - officeRule.earlyGraceMinutes);
        earlyMinutes = Math.max(0, Math.round((graceEnd.getTime() - now.getTime()) / 60000));
        hasRule = true;
      } else {
        hasRule = false;
      }
    } else {
      hasRule = false;
    }

    if (!hasRule) {
      status = AttendanceStatus.UNCONFIGURED;
    } else if (earlyMinutes > 0 && status === AttendanceStatus.NORMAL) {
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
      include: { matchedOffice: { select: { id: true, name: true } } },
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
      include: {
        user: { select: { id: true, name: true, employeeNo: true, department: true, team: true } },
        matchedOffice: { select: { id: true, name: true } },
      },
      orderBy: { date: 'desc' },
    });
  }

  async findToday(userId: string) {
    const today = businessToday();
    const record = await this.prisma.attendanceRecord.findUnique({
      where: { userId_date: { userId, date: today } },
      include: { matchedOffice: true },
    });
    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: userId } });
    const rule = await this.resolveEffectiveRule(user.teamId);
    return { record, effectiveRule: rule };
  }
}

function monthRange(month?: string): { start: Date; end: Date } {
  const base = month ? toBusinessDateOnly(`${month}-01T12:00:00Z`) : businessToday();
  const start = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth(), 1));
  const end = new Date(Date.UTC(base.getUTCFullYear(), base.getUTCMonth() + 1, 1));
  return { start, end };
}
