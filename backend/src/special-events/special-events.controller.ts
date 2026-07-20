import { Body, Controller, Get, Param, Patch, Post } from '@nestjs/common';
import { Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { SpecialEventsService } from './special-events.service';
import { CreateSpecialEventDto } from './dto/create-special-event.dto';

@Controller('special-events')
export class SpecialEventsController {
  constructor(private specialEventsService: SpecialEventsService) {}

  @Roles(Role.LOCAL_HR)
  @Post()
  create(@Body() dto: CreateSpecialEventDto, @CurrentUser() user: AuthUser) {
    return this.specialEventsService.create(dto, user.id);
  }

  @Get()
  findAll() {
    return this.specialEventsService.findAll();
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.specialEventsService.findOne(id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch(':id/revoke')
  revoke(@Param('id') id: string, @CurrentUser() user: AuthUser) {
    return this.specialEventsService.revoke(id, user.id);
  }
}
