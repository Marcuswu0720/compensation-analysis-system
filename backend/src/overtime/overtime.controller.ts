import { Body, Controller, Get, Param, Patch, Post, Query } from '@nestjs/common';
import { ApprovalStatus, Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
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
}
