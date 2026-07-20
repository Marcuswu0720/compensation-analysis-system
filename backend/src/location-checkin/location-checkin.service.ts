import { BadRequestException, Injectable } from '@nestjs/common';
import { AuditAction, VerifyStatus } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';

interface UploadParams {
  userId: string;
  photoUrl: string;
  gpsLat: number;
  gpsLng: number;
  takenAt?: string;
  businessMetricValue?: number;
}

@Injectable()
export class LocationCheckinService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  // 6.3: 定位照片、记录时间、记录人三者必须一并保存；7.2: 两张照片间隔超阈值触发预警（记入审计日志作为质检介入依据）
  async upload(params: UploadParams) {
    const takenAt = params.takenAt ? new Date(params.takenAt) : new Date();

    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: params.userId } });
    const ruleTemplate = user.teamId
      ? await this.prisma.teamAttendanceRuleTemplate.findUnique({ where: { teamId: user.teamId } })
      : null;

    const photo = await this.prisma.locationCheckInPhoto.create({
      data: {
        userId: params.userId,
        photoUrl: params.photoUrl,
        gpsLat: params.gpsLat,
        gpsLng: params.gpsLng,
        takenAt,
        businessMetricValue: params.businessMetricValue,
      },
    });

    if (ruleTemplate?.photoIntervalThresholdMinutes) {
      const previous = await this.prisma.locationCheckInPhoto.findFirst({
        where: { userId: params.userId, id: { not: photo.id }, takenAt: { lt: takenAt } },
        orderBy: { takenAt: 'desc' },
      });
      if (previous) {
        const intervalMinutes = (takenAt.getTime() - previous.takenAt.getTime()) / 60000;
        if (intervalMinutes > ruleTemplate.photoIntervalThresholdMinutes) {
          await this.audit.log({
            entityType: 'LOCATION_CHECKIN_ANOMALY',
            entityId: photo.id,
            action: AuditAction.CREATE,
            operatorId: params.userId,
            detail: {
              note: '两次拍照间隔超过阈值，已通知质检团队介入（通知渠道待确认，见需求文档14.3）',
              intervalMinutes: Math.round(intervalMinutes),
              thresholdMinutes: ruleTemplate.photoIntervalThresholdMinutes,
              previousPhotoId: previous.id,
            },
          });
        }
      }
    }

    return photo;
  }

  findAll(filters: { userId?: string; teamId?: string; from?: string; to?: string; verifyStatus?: VerifyStatus }) {
    return this.prisma.locationCheckInPhoto.findMany({
      where: {
        userId: filters.userId,
        verifyStatus: filters.verifyStatus,
        takenAt: {
          gte: filters.from ? new Date(filters.from) : undefined,
          lte: filters.to ? new Date(filters.to) : undefined,
        },
        user: filters.teamId ? { teamId: filters.teamId } : undefined,
      },
      include: { user: { select: { id: true, name: true, employeeNo: true, team: true } } },
      orderBy: { takenAt: 'asc' },
    });
  }

  findPending() {
    return this.prisma.locationCheckInPhoto.findMany({
      where: { verifyStatus: VerifyStatus.PENDING },
      include: { user: { select: { id: true, name: true, employeeNo: true, team: true } } },
      orderBy: { takenAt: 'asc' },
    });
  }

  // 打卡轨迹：某员工某天的照片按时间顺序展示
  findTrajectory(userId: string, date: string) {
    const day = new Date(date);
    const start = new Date(day.getFullYear(), day.getMonth(), day.getDate());
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return this.prisma.locationCheckInPhoto.findMany({
      where: { userId, takenAt: { gte: start, lt: end } },
      orderBy: { takenAt: 'asc' },
    });
  }

  async verify(id: string, status: VerifyStatus, remark: string | undefined, operatorId: string) {
    const photo = await this.prisma.locationCheckInPhoto.findUniqueOrThrow({ where: { id } });
    if (photo.verifyStatus !== VerifyStatus.PENDING) {
      throw new BadRequestException('该记录已核实过，不能重复操作');
    }
    const updated = await this.prisma.locationCheckInPhoto.update({
      where: { id },
      data: { verifyStatus: status, verifiedById: operatorId, verifiedAt: new Date() },
    });

    await this.audit.log({
      entityType: 'LOCATION_CHECKIN',
      entityId: id,
      action: AuditAction.VERIFY,
      operatorId,
      detail: { status, remark },
    });

    return updated;
  }
}
