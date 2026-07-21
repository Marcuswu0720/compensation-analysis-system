import { BadRequestException, Injectable } from '@nestjs/common';
import { AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateShiftDto } from './dto/create-shift.dto';
import { UpdateShiftDto } from './dto/update-shift.dto';
import { BatchGenerateDto } from './dto/batch-generate.dto';
import { ChangeAssignmentDto } from './dto/change-assignment.dto';
import { toBusinessDateOnly } from '../common/date-utils';

@Injectable()
export class SchedulesService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  // --- Shift ---
  createShift(dto: CreateShiftDto) {
    return this.prisma.shift.create({ data: dto });
  }

  findShifts(teamId?: string) {
    return this.prisma.shift.findMany({ where: { teamId }, orderBy: { startTime: 'asc' } });
  }

  updateShift(id: string, dto: UpdateShiftDto) {
    return this.prisma.shift.update({ where: { id }, data: dto });
  }

  removeShift(id: string) {
    return this.prisma.shift.delete({ where: { id } });
  }

  // 5.2: 排班表支持按周期批量生成（按周/按月），跳过已存在排班的日期避免误覆盖
  async batchGenerate(dto: BatchGenerateDto, operatorId: string) {
    const shift = await this.prisma.shift.findUniqueOrThrow({ where: { id: dto.shiftId } });
    const from = toBusinessDateOnly(dto.dateFrom);
    const to = toBusinessDateOnly(dto.dateTo);
    if (to < from) {
      throw new BadRequestException('结束日期不能早于开始日期');
    }

    const created: string[] = [];
    const skipped: { userId: string; date: string }[] = [];

    for (const userId of dto.userIds) {
      const cur = new Date(from);
      while (cur <= to) {
        if (!dto.daysOfWeek || dto.daysOfWeek.includes(cur.getUTCDay())) {
          const date = new Date(cur);
          const existing = await this.prisma.scheduleAssignment.findFirst({
            where: { userId, date },
            orderBy: { createdAt: 'desc' },
          });
          if (existing) {
            skipped.push({ userId, date: date.toISOString().slice(0, 10) });
          } else {
            const assignment = await this.prisma.scheduleAssignment.create({
              data: { userId, shiftId: shift.id, date, isTemporary: false },
            });
            created.push(assignment.id);
          }
        }
        cur.setUTCDate(cur.getUTCDate() + 1);
      }
    }

    await this.audit.log({
      entityType: 'SCHEDULE_BATCH',
      entityId: shift.id,
      action: AuditAction.CREATE,
      operatorId,
      detail: { shiftId: shift.id, createdCount: created.length, skippedCount: skipped.length },
    });

    return { createdCount: created.length, skippedCount: skipped.length, skipped };
  }

  // 单个员工换班 / 临时加排班：追加变更记录而非覆盖，保证可追溯
  async changeAssignment(assignmentId: string, dto: ChangeAssignmentDto, operatorId: string) {
    const old = await this.prisma.scheduleAssignment.findUniqueOrThrow({ where: { id: assignmentId } });
    const newShift = await this.prisma.shift.findUniqueOrThrow({ where: { id: dto.newShiftId } });

    const now = new Date();
    const changed = await this.prisma.scheduleAssignment.create({
      data: {
        userId: old.userId,
        shiftId: newShift.id,
        date: old.date,
        isTemporary: true,
        changedFromId: old.id,
        changedBy: operatorId,
        changedAt: now,
      },
    });

    await this.audit.log({
      entityType: 'SCHEDULE_ASSIGNMENT',
      entityId: changed.id,
      action: AuditAction.UPDATE,
      operatorId,
      detail: { changedFrom: { id: old.id, shiftId: old.shiftId }, changedTo: { id: changed.id, shiftId: newShift.id } },
    });

    return changed;
  }

  // 临时加排班（原本无排班的日期）
  async addTemporaryAssignment(userId: string, shiftId: string, date: string, operatorId: string) {
    const assignment = await this.prisma.scheduleAssignment.create({
      data: { userId, shiftId, date: toBusinessDateOnly(date), isTemporary: true, changedBy: operatorId, changedAt: new Date() },
    });
    await this.audit.log({
      entityType: 'SCHEDULE_ASSIGNMENT',
      entityId: assignment.id,
      action: AuditAction.CREATE,
      operatorId,
      detail: { assignment },
    });
    return assignment;
  }

  // 取每个 (userId, date) 组合下最新一条记录作为当前生效排班
  async findCurrentAssignments(filters: { userId?: string; teamId?: string; from?: string; to?: string }) {
    const rows = await this.prisma.scheduleAssignment.findMany({
      where: {
        userId: filters.userId,
        date: filters.from || filters.to ? { gte: filters.from ? toBusinessDateOnly(filters.from) : undefined, lte: filters.to ? toBusinessDateOnly(filters.to) : undefined } : undefined,
        user: filters.teamId ? { teamId: filters.teamId } : undefined,
      },
      include: { shift: true, user: { select: { id: true, name: true, employeeNo: true } } },
      orderBy: { createdAt: 'asc' },
    });

    const latestByKey = new Map<string, (typeof rows)[number]>();
    for (const row of rows) {
      const key = `${row.userId}_${row.date.toISOString().slice(0, 10)}`;
      latestByKey.set(key, row); // 依赖 createdAt 升序遍历，后来者覆盖，保留最新
    }
    return Array.from(latestByKey.values());
  }

  // 排班变更历史（含被替换的历史记录）
  async findHistory(userId: string, date: string) {
    return this.prisma.scheduleAssignment.findMany({
      where: { userId, date: toBusinessDateOnly(date) },
      include: { shift: true },
      orderBy: { createdAt: 'asc' },
    });
  }
}
