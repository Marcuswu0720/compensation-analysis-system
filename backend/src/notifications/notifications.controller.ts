import { Controller, Get, Param, Patch, Query } from '@nestjs/common';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { NotificationsService } from './notifications.service';

@Controller('notifications')
export class NotificationsController {
  constructor(private notificationsService: NotificationsService) {}

  @Get()
  findMine(@Query('unreadOnly') unreadOnly: string | undefined, @CurrentUser() user: AuthUser) {
    return this.notificationsService.findMine(user.id, unreadOnly === 'true');
  }

  @Get('unread-count')
  unreadCount(@CurrentUser() user: AuthUser) {
    return this.notificationsService.unreadCount(user.id);
  }

  @Patch(':id/read')
  markRead(@Param('id') id: string, @CurrentUser() user: AuthUser) {
    return this.notificationsService.markRead(id, user.id);
  }

  @Patch('read-all')
  markAllRead(@CurrentUser() user: AuthUser) {
    return this.notificationsService.markAllRead(user.id);
  }
}
