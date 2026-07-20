import { Injectable } from '@nestjs/common';
import { AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateTeamDto } from './dto/create-team.dto';
import { UpdateTeamDto } from './dto/update-team.dto';
import { SetModeConfigDto } from './dto/set-mode-config.dto';
import { SetOfficeRuleDto } from './dto/set-office-rule.dto';

@Injectable()
export class TeamsService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  create(dto: CreateTeamDto) {
    return this.prisma.team.create({ data: dto });
  }

  findAll() {
    return this.prisma.team.findMany({
      include: { department: true, modeConfig: true, leader: { select: { id: true, name: true } } },
      orderBy: { createdAt: 'asc' },
    });
  }

  findOne(id: string) {
    return this.prisma.team.findUniqueOrThrow({
      where: { id },
      include: { department: true, modeConfig: true, ruleTemplate: true, members: true, shifts: true },
    });
  }

  update(id: string, dto: UpdateTeamDto) {
    return this.prisma.team.update({ where: { id }, data: dto });
  }

  remove(id: string) {
    return this.prisma.team.delete({ where: { id } });
  }

  // 第3.2节：团队/岗位与打卡模式的配置。组织架构调整时可随时改变映射，故独立建模而非硬编码。
  async setModeConfig(teamId: string, dto: SetModeConfigDto, operatorId: string) {
    const before = await this.prisma.teamAttendanceModeConfig.findUnique({ where: { teamId } });
    const after = await this.prisma.teamAttendanceModeConfig.upsert({
      where: { teamId },
      create: { teamId, mode: dto.mode, updatedBy: operatorId },
      update: { mode: dto.mode, updatedBy: operatorId },
    });
    await this.audit.log({
      entityType: 'TEAM_MODE_CONFIG',
      entityId: teamId,
      action: before ? AuditAction.UPDATE : AuditAction.CREATE,
      operatorId,
      detail: { before, after },
    });
    return after;
  }

  getModeConfig(teamId: string) {
    return this.prisma.teamAttendanceModeConfig.findUnique({ where: { teamId } });
  }

  // 10.3 办公室打卡规则：上下班时间、迟到/早退宽限时间
  async setOfficeRule(teamId: string, dto: SetOfficeRuleDto, operatorId: string) {
    const before = await this.prisma.officeAttendanceRule.findUnique({ where: { teamId } });
    const after = await this.prisma.officeAttendanceRule.upsert({
      where: { teamId },
      create: { teamId, ...dto, updatedBy: operatorId },
      update: { ...dto, updatedBy: operatorId },
    });
    await this.audit.log({
      entityType: 'OFFICE_ATTENDANCE_RULE',
      entityId: teamId,
      action: before ? AuditAction.UPDATE : AuditAction.CREATE,
      operatorId,
      detail: { before, after },
    });
    return after;
  }

  getOfficeRule(teamId: string) {
    return this.prisma.officeAttendanceRule.findUnique({ where: { teamId } });
  }
}
