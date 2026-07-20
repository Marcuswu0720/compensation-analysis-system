import { Injectable } from '@nestjs/common';
import { ApprovalStatus, AttendanceStatus } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';

function monthRange(month?: string): { start: Date; end: Date } {
  const now = month ? new Date(`${month}-01T00:00:00`) : new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  return { start, end };
}

@Injectable()
export class ReportsService {
  constructor(private prisma: PrismaService) {}

  // 9. 关键指标：出勤天数、迟到次数、早退次数、缺勤天数、请假天数、加班时长、定位打卡异常次数
  async summary(filters: { userId?: string; departmentId?: string; teamId?: string; month?: string }) {
    const { start, end } = monthRange(filters.month);

    const users = await this.prisma.user.findMany({
      where: {
        id: filters.userId,
        departmentId: filters.departmentId,
        teamId: filters.teamId,
        isActive: true,
      },
      select: { id: true, name: true, employeeNo: true, department: { select: { name: true } }, team: { select: { name: true } } },
    });

    const results = [];
    for (const user of users) {
      const records = await this.prisma.attendanceRecord.findMany({
        where: { userId: user.id, date: { gte: start, lt: end } },
      });
      const overtimeAgg = await this.prisma.overtimeApplication.aggregate({
        where: { userId: user.id, date: { gte: start, lt: end }, status: ApprovalStatus.APPROVED },
        _sum: { hours: true },
      });
      const locationAnomalyCount = await this.prisma.auditLog.count({
        where: {
          entityType: 'LOCATION_CHECKIN_ANOMALY',
          operatorId: user.id,
          operatedAt: { gte: start, lt: end },
        },
      });

      results.push({
        userId: user.id,
        name: user.name,
        employeeNo: user.employeeNo,
        department: user.department?.name,
        team: user.team?.name,
        normalDays: records.filter((r) => r.status === AttendanceStatus.NORMAL).length,
        fullAttendanceDays: records.filter((r) => r.status === AttendanceStatus.FULL_ATTENDANCE).length,
        lateCount: records.filter((r) => r.status === AttendanceStatus.LATE).length,
        earlyLeaveCount: records.filter((r) => r.status === AttendanceStatus.EARLY_LEAVE).length,
        absentDays: records.filter((r) => r.status === AttendanceStatus.ABSENT).length,
        leaveDays: records.filter((r) => r.status === AttendanceStatus.LEAVE).length,
        overtimeHours: overtimeAgg._sum.hours ?? 0,
        locationAnomalyCount,
        attendanceRate:
          records.length > 0
            ? Math.round(
                ((records.length - records.filter((r) => r.status === AttendanceStatus.ABSENT).length) / records.length) * 1000,
              ) / 10
            : 0,
      });
    }

    return results;
  }

  // 全局报表（总部只读）：按部门聚合
  async globalByDepartment(month?: string) {
    const summaries = await this.summary({ month });
    const grouped = new Map<string, { department: string; users: number; lateCount: number; absentDays: number; leaveDays: number; overtimeHours: number }>();
    for (const s of summaries) {
      const key = s.department ?? '未分配';
      if (!grouped.has(key)) {
        grouped.set(key, { department: key, users: 0, lateCount: 0, absentDays: 0, leaveDays: 0, overtimeHours: 0 });
      }
      const g = grouped.get(key)!;
      g.users += 1;
      g.lateCount += s.lateCount;
      g.absentDays += s.absentDays;
      g.leaveDays += s.leaveDays;
      g.overtimeHours += Number(s.overtimeHours);
    }
    return Array.from(grouped.values());
  }

  async exportCsv(filters: { departmentId?: string; teamId?: string; month?: string }) {
    const rows = await this.summary(filters);
    const header = ['工号', '姓名', '部门', '团队', '正常出勤天数', '全勤天数', '迟到次数', '早退次数', '缺勤天数', '请假天数', '加班时长', '定位打卡异常次数', '出勤率(%)'];
    const lines = [header.join(',')];
    for (const r of rows) {
      lines.push(
        [r.employeeNo, r.name, r.department ?? '', r.team ?? '', r.normalDays, r.fullAttendanceDays, r.lateCount, r.earlyLeaveCount, r.absentDays, r.leaveDays, r.overtimeHours, r.locationAnomalyCount, r.attendanceRate].join(','),
      );
    }
    return lines.join('\n');
  }
}
