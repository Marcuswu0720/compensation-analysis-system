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

  @Get('assignments')
  findCurrentAssignments(
    @Query('userId') userId?: string,
    @Query('teamId') teamId?: string,
    @Query('from') from?: string,
    @Query('to') to?: string,
  ) {
    return this.schedulesService.findCurrentAssignments({ userId, teamId, from, to });
  }

  @Get('assignments/history')
  findHistory(@Query('userId') userId: string, @Query('date') date: string) {
    return this.schedulesService.findHistory(userId, date);
  }
}
