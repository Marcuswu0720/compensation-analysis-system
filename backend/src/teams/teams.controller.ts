import { Body, Controller, Delete, Get, Param, Patch, Post, Put } from '@nestjs/common';
import { Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { TeamsService } from './teams.service';
import { CreateTeamDto } from './dto/create-team.dto';
import { UpdateTeamDto } from './dto/update-team.dto';
import { SetModeConfigDto } from './dto/set-mode-config.dto';
import { SetOfficeRuleDto } from './dto/set-office-rule.dto';

@Controller('teams')
export class TeamsController {
  constructor(private teamsService: TeamsService) {}

  @Roles(Role.LOCAL_HR)
  @Post()
  create(@Body() dto: CreateTeamDto) {
    return this.teamsService.create(dto);
  }

  @Get()
  findAll() {
    return this.teamsService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.teamsService.findOne(id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateTeamDto) {
    return this.teamsService.update(id, dto);
  }

  @Roles(Role.LOCAL_HR)
  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.teamsService.remove(id);
  }

  @Get(':id/mode-config')
  getModeConfig(@Param('id') id: string) {
    return this.teamsService.getModeConfig(id);
  }

  @Roles(Role.LOCAL_HR)
  @Put(':id/mode-config')
  setModeConfig(@Param('id') id: string, @Body() dto: SetModeConfigDto, @CurrentUser() user: AuthUser) {
    return this.teamsService.setModeConfig(id, dto, user.id);
  }

  @Get(':id/office-rule')
  getOfficeRule(@Param('id') id: string) {
    return this.teamsService.getOfficeRule(id);
  }

  @Roles(Role.LOCAL_HR)
  @Put(':id/office-rule')
  setOfficeRule(@Param('id') id: string, @Body() dto: SetOfficeRuleDto, @CurrentUser() user: AuthUser) {
    return this.teamsService.setOfficeRule(id, dto, user.id);
  }
}
