import { Body, Controller, Get, Param, Patch, Post, Query } from '@nestjs/common';
import { ApprovalStatus, Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { AllowHqWrite } from '../common/decorators/allow-hq-write.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { OvertimeService } from './overtime.service';
import { CreateOvertimeDto } from './dto/create-overtime.dto';
import { ApproveDto } from '../leave/dto/approve.dto';

@Controller('overtime')
export class OvertimeController {
  constructor(private overtimeService: OvertimeService) {}

  @Post('applications')
  create(@Body() dto: CreateOvertimeDto, @CurrentUser() user: AuthUser) {
    return this.overtimeService.createApplication(user.id, dto);
  }

  @Get('applications/me')
  findMine(@CurrentUser() user: AuthUser) {
    return this.overtimeService.findMyApplications(user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Get('applications')
  findAll(
    @Query('status') status?: ApprovalStatus,
    @Query('departmentId') departmentId?: string,
    @Query('teamId') teamId?: string,
  ) {
    return this.overtimeService.findApplications({ status, departmentId, teamId });
  }

  @Patch('applications/:id/cancel')
  cancel(@Param('id') id: string, @CurrentUser() user: AuthUser) {
    return this.overtimeService.cancel(id, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch('applications/:id/approve')
  approve(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.overtimeService.approve(id, dto.comment, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch('applications/:id/reject')
  reject(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.overtimeService.reject(id, dto.comment, user.id);
  }

  // 本地HR/HRIS 没有上级，其本人提交的申请改为总部特批（问题反馈 2.6）
  @Roles(Role.HQ)
  @Get('applications/special-pending')
  findPendingSpecialApprovals() {
    return this.overtimeService.findPendingSpecialApprovals();
  }

  @Roles(Role.HQ)
  @AllowHqWrite()
  @Patch('applications/:id/special-approve')
  specialApprove(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.overtimeService.specialApprove(id, dto.comment, user.id);
  }

  @Roles(Role.HQ)
  @AllowHqWrite()
  @Patch('applications/:id/special-reject')
  specialReject(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.overtimeService.specialReject(id, dto.comment, user.id);
  }
}
