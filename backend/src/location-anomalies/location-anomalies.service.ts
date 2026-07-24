import { BadRequestException, Injectable } from '@nestjs/common';
import { AnomalyReviewStatus, AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';

const ANOMALY_SELECT = {
  id: true,
  photoId: true,
  userId: true,
  intervalMinutes: true,
  thresholdMinutes: true,
  status: true,
  reviewNote: true,
  reviewedById: true,
  reviewedAt: true,
  createdAt: true,
  user: { select: { id: true, name: true, employeeNo: true, team: true } },
  photo: { select: { id: true, photoUrl: true, takenAt: true, gpsLat: true, gpsLng: true } },
} as const;

@Injectable()
export class LocationAnomaliesService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  findAll(status?: AnomalyReviewStatus) {
    return this.prisma.locationCheckinAnomaly.findMany({
      where: { status },
      select: ANOMALY_SELECT,
      orderBy: { createdAt: 'desc' },
    });
  }

  async review(id: string, reviewNote: string | undefined, operatorId: string) {
    const anomaly = await this.prisma.locationCheckinAnomaly.findUniqueOrThrow({ where: { id } });
    if (anomaly.status === AnomalyReviewStatus.REVIEWED) {
      throw new BadRequestException('该异常记录已核查过，不能重复操作');
    }
    const updated = await this.prisma.locationCheckinAnomaly.update({
      where: { id },
      data: { status: AnomalyReviewStatus.REVIEWED, reviewNote, reviewedById: operatorId, reviewedAt: new Date() },
      select: ANOMALY_SELECT,
    });
    await this.audit.log({
      entityType: 'LOCATION_CHECKIN_ANOMALY',
      entityId: id,
      action: AuditAction.VERIFY,
      operatorId,
      detail: { reviewNote },
    });
    return updated;
  }
}
