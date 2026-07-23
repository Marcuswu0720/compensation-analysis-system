import { Body, Controller, Delete, Get, Param, Post, Put } from '@nestjs/common';
import { Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { RuleTemplatesService } from './rule-templates.service';
import { UpsertRuleTemplateDto } from './dto/upsert-rule-template.dto';

@Controller('rule-templates')
export class RuleTemplatesController {
  constructor(private ruleTemplatesService: RuleTemplatesService) {}

  @Get()
  findAll() {
    return this.ruleTemplatesService.findAll();
  }

  @Get(':teamId')
  findOne(@Param('teamId') teamId: string) {
    return this.ruleTemplatesService.findOne(teamId);
  }

  @Roles(Role.LOCAL_HR)
  @Put(':teamId')
  upsert(@Param('teamId') teamId: string, @Body() dto: UpsertRuleTemplateDto, @CurrentUser() user: AuthUser) {
    return this.ruleTemplatesService.upsert(teamId, dto, user.id);
  }

  // 清除误配置的团队规则模板，恢复为按打卡模式决定的默认行为
  @Roles(Role.LOCAL_HR)
  @Delete(':teamId')
  remove(@Param('teamId') teamId: string, @CurrentUser() user: AuthUser) {
    return this.ruleTemplatesService.remove(teamId, user.id);
  }

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR)
  @Post('evaluate-business-metric')
  evaluate(@Body() body: { userId: string; date: string }, @CurrentUser() user: AuthUser) {
    return this.ruleTemplatesService.evaluateBusinessMetric(body.userId, body.date, user.id);
  }
}
