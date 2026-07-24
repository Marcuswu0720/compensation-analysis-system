import { Injectable } from '@nestjs/common';
import { Role } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';

interface CreateNotificationParams {
  userId: string;
  type: string;
  title: string; // 服务端兜底文案（中文），前端已知 type 时会改用 i18n + params 渲染
  message: string;
  params?: Record<string, string | number>; // 供前端 i18n 插值
  relatedEntityType?: string;
  relatedEntityId?: string;
}

@Injectable()
export class NotificationsService {
  constructor(private prisma: PrismaService) {}

  async notifyUsers(userIds: string[], payload: Omit<CreateNotificationParams, 'userId'>) {
    const uniqueIds = [...new Set(userIds)];
    if (uniqueIds.length === 0) return;
    await this.prisma.notification.createMany({
      data: uniqueIds.map((userId) => ({ userId, ...payload })),
    });
  }

  async notifyRoles(roles: Role[], payload: Omit<CreateNotificationParams, 'userId'>) {
    const users = await this.prisma.user.findMany({ where: { role: { in: roles }, isActive: true }, select: { id: true } });
    await this.notifyUsers(
      users.map((u) => u.id),
      payload,
    );
  }

  findMine(userId: string, unreadOnly?: boolean) {
    return this.prisma.notification.findMany({
      where: { userId, isRead: unreadOnly ? false : undefined },
      orderBy: { createdAt: 'desc' },
      take: 100,
    });
  }

  unreadCount(userId: string) {
    return this.prisma.notification.count({ where: { userId, isRead: false } });
  }

  async markRead(id: string, userId: string) {
    await this.prisma.notification.updateMany({ where: { id, userId }, data: { isRead: true } });
    return { ok: true };
  }

  async markAllRead(userId: string) {
    await this.prisma.notification.updateMany({ where: { userId, isRead: false }, data: { isRead: true } });
    return { ok: true };
  }
}
