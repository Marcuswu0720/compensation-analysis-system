import { Body, Controller, Get, Param, Patch, Query } from '@nestjs/common';
import { AnomalyReviewStatus, Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { LocationAnomaliesService } from './location-anomalies.service';
import { ReviewAnomalyDto } from './dto/review-anomaly.dto';

// 定位打卡异常核查：质检团队专属入口，总部只读查看（问题反馈 2.2/2.4.1）
@Controller('location-anomalies')
export class LocationAnomaliesController {
  constructor(private locationAnomaliesService: LocationAnomaliesService) {}

  @Roles(Role.QC_TEAM, Role.HQ, Role.LOCAL_HR)
  @Get()
  findAll(@Query('status') status?: AnomalyReviewStatus) {
    return this.locationAnomaliesService.findAll(status);
  }

  @Roles(Role.QC_TEAM)
  @Patch(':id/review')
  review(@Param('id') id: string, @Body() dto: ReviewAnomalyDto, @CurrentUser() user: AuthUser) {
    return this.locationAnomaliesService.review(id, dto.reviewNote, user.id);
  }
}
