import { BadRequestException, ForbiddenException, Injectable, NotFoundException } from '@nestjs/common';
import { AttendanceSource, AttendanceStatus, AuditAction, OfficeAssignmentMode, Role, VerifyStatus } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { OfficesService } from '../offices/offices.service';
import { combineBusinessDateAndTime, toBusinessDateOnly } from '../common/date-utils';

interface UploadParams {
  userId: string;
  photoBuffer: Buffer;
  mimeType: string;
  gpsLat: number;
  gpsLng: number;
  takenAt?: string;
  businessMetricValue?: number;
}

const PHOTO_LIST_SELECT = {
  id: true,
  userId: true,
  photoUrl: true,
  gpsLat: true,
  gpsLng: true,
  takenAt: true,
  verifiedById: true,
  verifiedAt: true,
  verifyStatus: true,
  businessMetricValue: true,
  monthlySummaryId: true,
  isWithinRange: true,
  createdAt: true,
} as const;

@Injectable()
export class LocationCheckinService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
    private offices: OfficesService,
  ) {}

  // 6.3: 定位照片、记录时间、记录人三者必须一并保存；7.2: 两张照片间隔超阈值触发预警（记入审计日志作为质检介入依据）
  // 照片二进制内容直接存数据库（而非本地磁盘），避免云端免费实例磁盘不持久导致审核后照片打不开（问题反馈 4.2）
  async upload(params: UploadParams) {
    const takenAt = params.takenAt ? new Date(params.takenAt) : new Date();

    const user = await this.prisma.user.findUniqueOrThrow({ where: { id: params.userId } });
    const ruleTemplate = user.teamId
      ? await this.prisma.teamAttendanceRuleTemplate.findUnique({ where: { teamId: user.teamId }, include: { offices: true } })
      : null;

    // 码牌团队"定位范围内打卡"（问题反馈 2.5）：officeAssignmentMode 为 FIXED 且关联了有效地点时，
    // 校验 GPS 是否落在允许半径内，仅作标记不阻断打卡（业务方尚未确认是否要强制拦截）
    const isWithinRange =
      ruleTemplate?.officeAssignmentMode === OfficeAssignmentMode.FIXED && ruleTemplate.offices.length > 0
        ? !!this.offices.findNearestWithin(params.gpsLat, params.gpsLng, ruleTemplate.offices)
        : null;

    const created = await this.prisma.locationCheckInPhoto.create({
      data: {
        userId: params.userId,
        photoUrl: '', // 下面用自身 id 回填
        photoData: new Uint8Array(params.photoBuffer),
        photoMimeType: params.mimeType,
        gpsLat: params.gpsLat,
        gpsLng: params.gpsLng,
        takenAt,
        businessMetricValue: params.businessMetricValue,
        isWithinRange,
      },
    });
    const photo = await this.prisma.locationCheckInPhoto.update({
      where: { id: created.id },
      data: { photoUrl: `/api/location-checkin/${created.id}/photo` },
      select: PHOTO_LIST_SELECT,
    });

    // 拍照打卡此前只写入 LocationCheckInPhoto，从不创建/更新 AttendanceRecord，导致"今日状态"模块
    // （查询 AttendanceRecord）对定位打卡团队永远看不到任何记录（问题反馈 2.6）。这里在首次上传时
    // 补一条"待核实"记录，核实通过后在 verify() 里推进为"正常"。
    const businessDate = toBusinessDateOnly(takenAt);
    await this.prisma.attendanceRecord.upsert({
      where: { userId_date: { userId: params.userId, date: businessDate } },
      create: {
        userId: params.userId,
        date: businessDate,
        clockInAt: takenAt,
        status: AttendanceStatus.PENDING,
        source: AttendanceSource.LOCATION_CLOCK,
      },
      update: {},
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

  async getPhotoBinary(id: string) {
    const photo = await this.prisma.locationCheckInPhoto.findUnique({
      where: { id },
      select: { photoData: true, photoMimeType: true },
    });
    if (!photo) {
      throw new NotFoundException('照片不存在');
    }
    return photo;
  }

  findAll(
    filters: { userId?: string; teamId?: string; from?: string; to?: string; verifyStatus?: VerifyStatus },
    operator: { id: string; role: Role },
  ) {
    return this.prisma.locationCheckInPhoto.findMany({
      where: {
        userId: filters.userId,
        verifyStatus: filters.verifyStatus,
        takenAt: {
          gte: filters.from ? new Date(filters.from) : undefined,
          lte: filters.to ? new Date(filters.to) : undefined,
        },
        user: { teamId: filters.teamId, ...this.excludeOwnLedTeam(operator) },
      },
      select: { ...PHOTO_LIST_SELECT, user: { select: { id: true, name: true, employeeNo: true, team: true } } },
      orderBy: { takenAt: 'asc' },
    });
  }

  findPending(operator: { id: string; role: Role }) {
    return this.prisma.locationCheckInPhoto.findMany({
      where: { verifyStatus: VerifyStatus.PENDING, user: this.excludeOwnLedTeam(operator) },
      select: { ...PHOTO_LIST_SELECT, user: { select: { id: true, name: true, employeeNo: true, team: true } } },
      orderBy: { takenAt: 'asc' },
    });
  }

  // 团队 Manager 不能审核自己所带团队的定位打卡记录，需上一级（本地HR）审核（问题反馈 2.1）
  // team 是可选关系：isNot 在关联为空或关联存在但不匹配时都成立，正好覆盖"未分配团队的员工仍应正常显示"的情况
  private excludeOwnLedTeam(operator: { id: string; role: Role }) {
    if (operator.role !== Role.LOCAL_MANAGER) return {};
    return { team: { isNot: { leaderId: operator.id } } };
  }

  // 打卡轨迹：某员工某天的照片按时间顺序展示（按业务时区取自然日边界，见问题反馈 2.5 的统一处理方式）
  findTrajectory(userId: string, date: string) {
    const start = combineBusinessDateAndTime(toBusinessDateOnly(date), '00:00');
    const end = new Date(start.getTime() + 24 * 60 * 60000);
    return this.prisma.locationCheckInPhoto.findMany({
      where: { userId, takenAt: { gte: start, lt: end } },
      select: PHOTO_LIST_SELECT,
      orderBy: { takenAt: 'asc' },
    });
  }

  async verify(id: string, status: VerifyStatus, remark: string | undefined, operator: { id: string; role: Role }) {
    const photo = await this.prisma.locationCheckInPhoto.findUniqueOrThrow({ where: { id }, include: { user: { include: { team: true } } } });
    if (photo.verifyStatus !== VerifyStatus.PENDING) {
      throw new BadRequestException('该记录已核实过，不能重复操作');
    }
    if (operator.role === Role.LOCAL_MANAGER && photo.user.team?.leaderId === operator.id) {
      throw new ForbiddenException('不能审核本团队自己的打卡记录，请联系本地HR审核');
    }
    const updated = await this.prisma.locationCheckInPhoto.update({
      where: { id },
      data: { verifyStatus: status, verifiedById: operator.id, verifiedAt: new Date() },
      select: PHOTO_LIST_SELECT,
    });

    await this.audit.log({
      entityType: 'LOCATION_CHECKIN',
      entityId: id,
      action: AuditAction.VERIFY,
      operatorId: operator.id,
      detail: { status, remark },
    });

    // 核实通过后，把当天"待核实"的考勤记录推进为"正常"，使"今日状态"能反映最终结果（问题反馈 2.6）
    if (status === VerifyStatus.APPROVED) {
      const businessDate = toBusinessDateOnly(photo.takenAt);
      const record = await this.prisma.attendanceRecord.findUnique({
        where: { userId_date: { userId: photo.userId, date: businessDate } },
      });
      if (record && record.status === AttendanceStatus.PENDING) {
        await this.prisma.attendanceRecord.update({ where: { id: record.id }, data: { status: AttendanceStatus.NORMAL } });
      }
    }

    return updated;
  }
}
