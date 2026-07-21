import { Body, Controller, Get, Param, Patch, Post, Query } from '@nestjs/common';
import { ApprovalStatus, Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { AllowHqWrite } from '../common/decorators/allow-hq-write.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { LeaveService } from './leave.service';
import { CreateLeaveTypeDto } from './dto/create-leave-type.dto';
import { CreateLeaveApplicationDto } from './dto/create-leave-application.dto';
import { ApproveDto } from './dto/approve.dto';

@Controller('leave')
export class LeaveController {
  constructor(private leaveService: LeaveService) {}

  @Roles(Role.LOCAL_HR)
  @Post('types')
  createType(@Body() dto: CreateLeaveTypeDto) {
    return this.leaveService.createLeaveType(dto);
  }

  @Get('types')
  findTypes(@Query('activeOnly') activeOnly?: string) {
    return this.leaveService.findLeaveTypes(activeOnly === 'true');
  }

  @Roles(Role.LOCAL_HR)
  @Patch('types/:id/active')
  setTypeActive(@Param('id') id: string, @Body('isActive') isActive: boolean) {
    return this.leaveService.setLeaveTypeActive(id, isActive);
  }

  @Post('applications')
  create(@Body() dto: CreateLeaveApplicationDto, @CurrentUser() user: AuthUser) {
    return this.leaveService.createApplication(user.id, dto);
  }

  @Get('applications/me')
  findMine(@CurrentUser() user: AuthUser) {
    return this.leaveService.findMyApplications(user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Get('applications')
  findAll(
    @Query('status') status?: ApprovalStatus,
    @Query('departmentId') departmentId?: string,
    @Query('teamId') teamId?: string,
  ) {
    return this.leaveService.findApplications({ status, departmentId, teamId });
  }

  @Patch('applications/:id/cancel')
  cancel(@Param('id') id: string, @CurrentUser() user: AuthUser) {
    return this.leaveService.cancel(id, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch('applications/:id/approve')
  approve(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.leaveService.approve(id, dto.comment, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch('applications/:id/reject')
  reject(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.leaveService.reject(id, dto.comment, user.id);
  }

  // 本地HR/HRIS 没有上级，其本人提交的申请不能走普通审批（会形成自申自批），改为总部特批（问题反馈 2.6）
  @Roles(Role.HQ)
  @Get('applications/special-pending')
  findPendingSpecialApprovals() {
    return this.leaveService.findPendingSpecialApprovals();
  }

  @Roles(Role.HQ)
  @AllowHqWrite()
  @Patch('applications/:id/special-approve')
  specialApprove(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.leaveService.specialApprove(id, dto.comment, user.id);
  }

  @Roles(Role.HQ)
  @AllowHqWrite()
  @Patch('applications/:id/special-reject')
  specialReject(@Param('id') id: string, @Body() dto: ApproveDto, @CurrentUser() user: AuthUser) {
    return this.leaveService.specialReject(id, dto.comment, user.id);
  }
}
