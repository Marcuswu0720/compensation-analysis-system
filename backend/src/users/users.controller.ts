import {
  Body,
  Controller,
  Get,
  Param,
  Patch,
  Post,
  Query,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { UsersService } from './users.service';
import { CreateUserDto } from './dto/create-user.dto';
import { UpdateUserDto } from './dto/update-user.dto';

@Controller('users')
export class UsersController {
  constructor(private usersService: UsersService) {}

  @Roles(Role.LOCAL_HR)
  @Post()
  create(@Body() dto: CreateUserDto, @CurrentUser() user: AuthUser) {
    return this.usersService.create(dto, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Post('import')
  @UseInterceptors(FileInterceptor('file'))
  importFromExcel(@UploadedFile() file: Express.Multer.File, @CurrentUser() user: AuthUser) {
    return this.usersService.importFromExcel(file.buffer, user.id);
  }

  @Get()
  findAll(
    @Query('departmentId') departmentId?: string,
    @Query('teamId') teamId?: string,
    @Query('keyword') keyword?: string,
  ) {
    return this.usersService.findAll({ departmentId, teamId, keyword });
  }

  @Get('me')
  findMe(@CurrentUser() user: AuthUser) {
    return this.usersService.findOne(user.id);
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.usersService.findOne(id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateUserDto, @CurrentUser() user: AuthUser) {
    return this.usersService.update(id, dto, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch(':id/enable')
  enable(@Param('id') id: string, @CurrentUser() user: AuthUser) {
    return this.usersService.setActive(id, true, user.id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch(':id/disable')
  disable(@Param('id') id: string, @CurrentUser() user: AuthUser) {
    return this.usersService.setActive(id, false, user.id);
  }
}
