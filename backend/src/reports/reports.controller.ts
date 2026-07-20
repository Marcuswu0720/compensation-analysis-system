import { Controller, Get, Query, Res } from '@nestjs/common';
import { Response } from 'express';
import { Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { ReportsService } from './reports.service';

@Controller('reports')
export class ReportsController {
  constructor(private reportsService: ReportsService) {}

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR, Role.HQ)
  @Get('summary')
  summary(
    @Query('userId') userId?: string,
    @Query('departmentId') departmentId?: string,
    @Query('teamId') teamId?: string,
    @Query('month') month?: string,
  ) {
    return this.reportsService.summary({ userId, departmentId, teamId, month });
  }

  @Roles(Role.HQ, Role.LOCAL_HR)
  @Get('global')
  global(@Query('month') month?: string) {
    return this.reportsService.globalByDepartment(month);
  }

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR, Role.HQ)
  @Get('export')
  async export(
    @Query('departmentId') departmentId: string | undefined,
    @Query('teamId') teamId: string | undefined,
    @Query('month') month: string | undefined,
    @Res() res: Response,
  ) {
    const csv = await this.reportsService.exportCsv({ departmentId, teamId, month });
    res.header('Content-Type', 'text/csv; charset=utf-8');
    res.attachment(`attendance-report-${month ?? 'current'}.csv`);
    res.send('﻿' + csv);
  }
}
