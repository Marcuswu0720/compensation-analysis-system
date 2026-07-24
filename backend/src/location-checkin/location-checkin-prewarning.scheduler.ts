import { Injectable, Logger } from '@nestjs/common';
import { Cron, CronExpression } from '@nestjs/schedule';
import { PrismaService } from '../prisma/prisma.service';
import { NotificationsService } from '../notifications/notifications.service';

// 码牌团队"快超时"提前提醒（问题反馈 2.4.2）：按团队配置的阈值/提前提醒分钟数，
// 定期检查每个需要拍照打卡的员工距上次打卡是否即将超过间隔阈值，提前通知员工本人。
@Injectable()
export class LocationCheckinPreWarningScheduler {
  private readonly logger = new Logger(LocationCheckinPreWarningScheduler.name);

  constructor(
    private prisma: PrismaService,
    private notifications: NotificationsService,
  ) {}

  @Cron(CronExpression.EVERY_MINUTE)
  async checkPreWarnings() {
    const templates = await this.prisma.teamAttendanceRuleTemplate.findMany({
      where: {
        requiresPhoto: true,
        photoIntervalThresholdMinutes: { not: null },
        photoIntervalPreWarnMinutes: { not: null },
      },
    });
    if (templates.length === 0) return;

    for (const template of templates) {
      const threshold = template.photoIntervalThresholdMinutes!;
      const preWarn = template.photoIntervalPreWarnMinutes!;
      const users = await this.prisma.user.findMany({ where: { teamId: template.teamId, isActive: true } });

      for (const user of users) {
        const lastPhoto = await this.prisma.locationCheckInPhoto.findFirst({
          where: { userId: user.id },
          orderBy: { takenAt: 'desc' },
        });
        if (!lastPhoto) continue;

        const elapsedMinutes = (Date.now() - lastPhoto.takenAt.getTime()) / 60000;
        const warnAtMinutes = threshold - preWarn;
        if (elapsedMinutes < warnAtMinutes || elapsedMinutes >= threshold) continue;

        // 去重：同一张"上一次打卡照片"对应的即将超时窗口内只提醒一次，避免每分钟重复发送
        const alreadyWarned = await this.prisma.notification.findFirst({
          where: { userId: user.id, type: 'LOCATION_ANOMALY_PRE_WARNING', relatedEntityId: lastPhoto.id },
        });
        if (alreadyWarned) continue;

        const remainingMinutes = Math.max(0, Math.round(threshold - elapsedMinutes));
        await this.notifications.notifyUsers([user.id], {
          type: 'LOCATION_ANOMALY_PRE_WARNING',
          title: '定位打卡即将超时',
          message: `距上次打卡已过 ${Math.round(elapsedMinutes)} 分钟，请在 ${remainingMinutes} 分钟内完成下一次定位打卡，避免生成异常记录`,
          params: { remainingMinutes, thresholdMinutes: threshold },
          relatedEntityType: 'LOCATION_CHECKIN_PHOTO',
          relatedEntityId: lastPhoto.id,
        });
        this.logger.log(`Sent pre-warning to user ${user.id} (${remainingMinutes}min remaining)`);
      }
    }
  }
}
