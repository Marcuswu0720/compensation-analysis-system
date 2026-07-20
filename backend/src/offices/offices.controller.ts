import { Body, Controller, Delete, Get, Param, Patch, Post, Query } from '@nestjs/common';
import { Role } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { OfficesService } from './offices.service';
import { CreateOfficeDto } from './dto/create-office.dto';
import { UpdateOfficeDto } from './dto/update-office.dto';

@Controller('offices')
export class OfficesController {
  constructor(private officesService: OfficesService) {}

  @Roles(Role.LOCAL_HR)
  @Post()
  create(@Body() dto: CreateOfficeDto) {
    return this.officesService.create(dto);
  }

  @Get()
  findAll() {
    return this.officesService.findAll();
  }

  @Get('nearest')
  findNearest(@Query('lat') lat: string, @Query('lng') lng: string) {
    return this.officesService.findNearest(parseFloat(lat), parseFloat(lng));
  }

  @Get(':id')
  findOne(@Param('id') id: string) {
    return this.officesService.findOne(id);
  }

  @Roles(Role.LOCAL_HR)
  @Patch(':id')
  update(@Param('id') id: string, @Body() dto: UpdateOfficeDto) {
    return this.officesService.update(id, dto);
  }

  @Roles(Role.LOCAL_HR)
  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.officesService.remove(id);
  }
}
