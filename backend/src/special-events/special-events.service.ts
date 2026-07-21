import { BadRequestException, Injectable } from '@nestjs/common';
import { AttendanceSource, AttendanceStatus, AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateSpecialEventDto } from './dto/create-special-event.dto';
import { eachBusinessDate } from '../common/date-utils';

@Injectable()
export class SpecialEventsService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  // 4.2 触发后：为受影响范围内员工（按办公室圈定）在生效期间自动生成全勤记录，跳过正常打卡流程
  async create(dto: CreateSpecialEventDto, operatorId: string) {
    const startTime = new Date(dto.startTime);
    const endTime = new Date(dto.endTime);
    if (endTime < startTime) {
      throw new BadRequestException('结束时间不能早于开始时间');
    }

    const event = await this.prisma.specialAttendanceEvent.create({
      data: {
        type: dto.type,
        startTime,
        endTime,
        createdById: operatorId,
        remark: dto.remark,
        affectedOffices: { create: dto.affectedOfficeIds.map((officeId) => ({ officeId })) },
      },
      include: { affectedOffices: { include: { office: true } } },
    });

    const affectedUsers = await this.prisma.user.findMany({
      where: { officeId: { in: dto.affectedOfficeIds }, isActive: true },
      select: { id: true },
    });

    const days = eachBusinessDate(startTime, endTime);
    for (const user of affectedUsers) {
      for (const day of days) {
        await this.prisma.attendanceRecord.upsert({
          where: { userId_date: { userId: user.id, date: day } },
          create: {
            userId: user.id,
            date: day,
            status: AttendanceStatus.FULL_ATTENDANCE,
            source: AttendanceSource.SPECIAL_EVENT_AUTO,
            specialEventId: event.id,
            remark: `${dto.type === 'EXTREME_WEATHER' ? '极端天气' : '突发事件'}自动全勤`,
          },
          update: {
            status: AttendanceStatus.FULL_ATTENDANCE,
            source: AttendanceSource.SPECIAL_EVENT_AUTO,
            specialEventId: event.id,
            remark: `${dto.type === 'EXTREME_WEATHER' ? '极端天气' : '突发事件'}自动全勤`,
          },
        });
      }
    }

    await this.audit.log({
      entityType: 'SPECIAL_EVENT',
      entityId: event.id,
      action: AuditAction.CREATE,
      operatorId,
      detail: { affectedOfficeIds: dto.affectedOfficeIds, startTime, endTime, affectedUserCount: affectedUsers.length },
    });

    return event;
  }

  findAll() {
    return this.prisma.specialAttendanceEvent.findMany({
      include: {
        affectedOffices: { include: { office: true } },
        createdBy: { select: { id: true, name: true } },
        revokedBy: { select: { id: true, name: true } },
      },
      orderBy: { createdAt: 'desc' },
    });
  }

  findOne(id: string) {
    return this.prisma.specialAttendanceEvent.findUniqueOrThrow({
      where: { id },
      include: { affectedOffices: { include: { office: true } } },
    });
  }

  // 撤销：留痕撤销人/撤销时间；已生成但未实际打卡的自动全勤记录回退
  async revoke(id: string, operatorId: string) {
    const event = await this.prisma.specialAttendanceEvent.findUniqueOrThrow({ where: { id } });
    if (event.revokedAt) {
      throw new BadRequestException('该事件已被撤销');
    }

    const revoked = await this.prisma.specialAttendanceEvent.update({
      where: { id },
      data: { revokedById: operatorId, revokedAt: new Date() },
    });

    await this.prisma.attendanceRecord.updateMany({
      where: { specialEventId: id, source: AttendanceSource.SPECIAL_EVENT_AUTO, clockInAt: null },
      data: { status: AttendanceStatus.ABSENT, remark: '特殊事件已撤销，全勤标记已回退' },
    });

    await this.audit.log({
      entityType: 'SPECIAL_EVENT',
      entityId: id,
      action: AuditAction.REVOKE,
      operatorId,
      detail: { revokedAt: revoked.revokedAt },
    });

    return revoked;
  }
}
