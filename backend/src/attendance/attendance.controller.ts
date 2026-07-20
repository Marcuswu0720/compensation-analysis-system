import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { Role } from '@prisma/client';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { Roles } from '../common/decorators/roles.decorator';
import { AuthUser } from '../auth/auth.types';
import { AttendanceService } from './attendance.service';
import { ClockInDto } from './dto/clock-in.dto';
import { ClockOutDto } from './dto/clock-out.dto';

@Controller('attendance')
export class AttendanceController {
  constructor(private attendanceService: AttendanceService) {}

  @Post('clock-in')
  clockIn(@Body() dto: ClockInDto, @CurrentUser() user: AuthUser) {
    return this.attendanceService.clockIn(user.id, dto);
  }

  @Post('clock-out')
  clockOut(@Body() dto: ClockOutDto, @CurrentUser() user: AuthUser) {
    return this.attendanceService.clockOut(user.id, dto);
  }

  @Get('today')
  findToday(@CurrentUser() user: AuthUser) {
    return this.attendanceService.findToday(user.id);
  }

  @Get('me')
  findMyCalendar(@Query('month') month: string | undefined, @CurrentUser() user: AuthUser) {
    return this.attendanceService.findMyCalendar(user.id, month);
  }

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR, Role.HQ)
  @Get()
  findAll(
    @Query('userId') userId?: string,
    @Query('departmentId') departmentId?: string,
    @Query('teamId') teamId?: string,
    @Query('month') month?: string,
  ) {
    return this.attendanceService.findAll({ userId, departmentId, teamId, month });
  }
}
