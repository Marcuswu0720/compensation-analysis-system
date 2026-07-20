import { Controller, Get, Query } from '@nestjs/common';
import { Roles } from '../decorators/roles.decorator';
import { Role } from '@prisma/client';
import { AuditService } from './audit.service';

@Controller('audit-logs')
@Roles(Role.LOCAL_HR, Role.HQ)
export class AuditController {
  constructor(private auditService: AuditService) {}

  @Get()
  findAll(
    @Query('entityType') entityType?: string,
    @Query('entityId') entityId?: string,
    @Query('operatorId') operatorId?: string,
  ) {
    return this.auditService.findAll({ entityType, entityId, operatorId });
  }
}
