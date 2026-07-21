import { Body, Controller, Delete, Get, Param, Patch, Post, Query } from '@nestjs/common';
import { Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { SchedulesService } from './schedules.service';
import { CreateShiftDto } from './dto/create-shift.dto';
import { UpdateShiftDto } from './dto/update-shift.dto';
import { BatchGenerateDto } from './dto/batch-generate.dto';
import { ChangeAssignmentDto } from './dto/change-assignment.dto';

@Controller('schedules')
export class SchedulesController {
  constructor(private schedulesService: SchedulesService) {}

  @Roles(Role.LOCAL_HR)
  @Post('shifts')
  createShift(@Body() dto: CreateShiftDto) {
    return this.schedulesService.createShift(dto);
  }

  @Get('shifts')
  findShifts(@Query('teamId') teamId?: string) {
    return this.schedulesService.findShifts(teamId);
  }

  @Roles(Role.LOCAL_HR)
  @Patch('shifts/:id')
  updateShift(@Param('id') id: string, @Body() dto: UpdateShiftDto) {
    return this.schedulesService.updateShift(id, dto);
  }

  @Roles(Role.LOCAL_HR)
  @Delete('shifts/:id')
  removeShift(@Param('id') id: string) {
    return this.schedulesService.removeShift(id);
  }

  @Roles(Role.LOCAL_HR)
  @Post('assignments/batch-generate')
  batchGenerate(@Body() dto: BatchGenerateDto, @CurrentUser() user: AuthUser) {
    return this.schedulesService.batchGenerate(dto, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch('assignments/:id/change')
  changeAssignment(@Param('id') id: string, @Body() dto: ChangeAssignmentDto, @CurrentUser() user: AuthUser) {
    return this.schedulesService.changeAssignment(id, dto, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Post('assignments/temporary')
  addTemporary(
    @Body() body: { userId: string; shiftId: string; date: string },
    @CurrentUser() user: AuthUser,
  ) {
    return this.schedulesService.addTemporaryAssignment(body.userId, body.shiftId, body.date, user.id);
  }

  // 普通员工只能查看自己所在团队的排班，接口层强制按登录用户过滤 —— 不能依赖前端隐藏其他团队数据，
  // 否则可以直接改查询参数拿到全量数据（问题反馈 3.1，数据安全问题）
  @Get('assignments')
  findCurrentAssignments(
    @Query('userId') userId: string | undefined,
    @Query('teamId') teamId: string | undefined,
    @Query('from') from: string | undefined,
    @Query('to') to: string | undefined,
    @CurrentUser() user: AuthUser,
  ) {
    if (user.role === Role.EMPLOYEE) {
      // 员工可以看到本团队完整排班（含同事），但团队范围被强制锁定为自己所在团队，忽略客户端传入的 teamId
      return this.schedulesService.findCurrentAssignments({ userId, teamId: user.teamId ?? '__none__', from, to });
    }
    return this.schedulesService.findCurrentAssignments({ userId, teamId, from, to });
  }

  @Get('assignments/history')
  findHistory(@Query('userId') userId: string, @Query('date') date: string, @CurrentUser() user: AuthUser) {
    if (user.role === Role.EMPLOYEE) {
      return this.schedulesService.findHistory(user.id, date);
    }
    return this.schedulesService.findHistory(userId, date);
  }
}
