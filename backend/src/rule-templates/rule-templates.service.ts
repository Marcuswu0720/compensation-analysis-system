import { Injectable } from '@nestjs/common';
import { AttendanceSource, AttendanceStatus, AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { UpsertRuleTemplateDto } from './dto/upsert-rule-template.dto';

@Injectable()
export class RuleTemplatesService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  findOne(teamId: string) {
    return this.prisma.teamAttendanceRuleTemplate.findUnique({ where: { teamId } });
  }

  findAll() {
    return this.prisma.teamAttendanceRuleTemplate.findMany({ include: { team: true } });
  }

  async upsert(teamId: string, dto: UpsertRuleTemplateDto, operatorId: string) {
    const before = await this.prisma.teamAttendanceRuleTemplate.findUnique({ where: { teamId } });
    const after = await this.prisma.teamAttendanceRuleTemplate.upsert({
      where: { teamId },
      create: { teamId, ...dto },
      update: dto,
    });
    await this.audit.log({
      entityType: 'RULE_CONFIG',
      entityId: teamId,
      action: before ? AuditAction.UPDATE : AuditAction.CREATE,
      operatorId,
      detail: { before, after },
    });
    return after;
  }

  // 清除该团队的规则模板覆盖，恢复为按打卡模式（办公室/排班/定位）决定的默认行为
  async remove(teamId: string, operatorId: string) {
    const before = await this.prisma.teamAttendanceRuleTemplate.findUnique({ where: { teamId } });
    if (!before) return { removed: false };
    await this.prisma.teamAttendanceRuleTemplate.delete({ where: { teamId } });
    await this.audit.log({
      entityType: 'RULE_CONFIG',
      entityId: teamId,
      action: AuditAction.DELETE,
      operatorId,
      detail: { before, after: null },
    });
    return { removed: true };
  }

  // 7.2 业务指标对接判断出勤：如码牌团队"超过8家算出勤"。
  // 数据来源待确认（API对接 or 人工录入），此处按当日 LocationCheckInPhoto.businessMetricValue 之和判断（人工录入路径）。
  async evaluateBusinessMetric(userId: string, date: string, operatorId: string) {
    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: userId } });
    const template = user.teamId
      ? await this.prisma.teamAttendanceRuleTemplate.findUnique({ where: { teamId: user.teamId } })
      : null;
    if (!template?.requiresBusinessMetric || !template.businessMetricThreshold) {
      throw new Error('该团队未启用业务指标出勤判定');
    }

    const day = new Date(date);
    const start = new Date(day.getFullYear(), day.getMonth(), day.getDate());
    const end = new Date(start);
    end.setDate(end.getDate() + 1);

    const photos = await this.prisma.locationCheckInPhoto.findMany({
      where: { userId, takenAt: { gte: start, lt: end } },
    });
    const total = photos.reduce((sum, p) => sum + (p.businessMetricValue ?? 0), 0);
    const attained = total >= template.businessMetricThreshold;

    const record = await this.prisma.attendanceRecord.upsert({
      where: { userId_date: { userId, date: start } },
      create: {
        userId,
        date: start,
        status: attained ? AttendanceStatus.NORMAL : AttendanceStatus.ABSENT,
        source: AttendanceSource.LOCATION_CLOCK,
        remark: `业务指标出勤判定：当日 ${total}/${template.businessMetricThreshold}`,
      },
      update: {
        status: attained ? AttendanceStatus.NORMAL : AttendanceStatus.ABSENT,
        remark: `业务指标出勤判定：当日 ${total}/${template.businessMetricThreshold}`,
      },
    });

    await this.audit.log({
      entityType: 'BUSINESS_METRIC_ATTENDANCE',
      entityId: record.id,
      action: AuditAction.UPDATE,
      operatorId,
      detail: { total, threshold: template.businessMetricThreshold, attained },
    });

    return record;
  }
}
