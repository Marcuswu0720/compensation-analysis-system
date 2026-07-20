import { BadRequestException, Body, Controller, Get, Param, Patch, Post, Query, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import { extname } from 'path';
import { randomUUID } from 'crypto';
import { Role, VerifyStatus } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { AuthUser } from '../auth/auth.types';
import { LocationCheckinService } from './location-checkin.service';
import { VerifyPhotoDto } from './dto/verify-photo.dto';

@Controller('location-checkin')
export class LocationCheckinController {
  constructor(private locationCheckinService: LocationCheckinService) {}

  @Post()
  @UseInterceptors(
    FileInterceptor('photo', {
      storage: diskStorage({
        destination: process.env.UPLOAD_DIR ?? './uploads',
        filename: (_req, file, cb) => cb(null, `${randomUUID()}${extname(file.originalname)}`),
      }),
      limits: { fileSize: 10 * 1024 * 1024 },
    }),
  )
  upload(
    @UploadedFile() file: Express.Multer.File,
    @Body() body: { lat: string; lng: string; takenAt?: string; businessMetricValue?: string },
    @CurrentUser() user: AuthUser,
  ) {
    if (!file) {
      throw new BadRequestException('未上传照片');
    }
    return this.locationCheckinService.upload({
      userId: user.id,
      photoUrl: `/uploads/${file.filename}`,
      gpsLat: parseFloat(body.lat),
      gpsLng: parseFloat(body.lng),
      takenAt: body.takenAt,
      businessMetricValue: body.businessMetricValue ? parseInt(body.businessMetricValue, 10) : undefined,
    });
  }

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR)
  @Get('pending')
  findPending() {
    return this.locationCheckinService.findPending();
  }

  @Get('trajectory')
  findTrajectory(@Query('userId') userId: string, @Query('date') date: string) {
    return this.locationCheckinService.findTrajectory(userId, date);
  }

  @Get()
  findAll(
    @Query('userId') userId?: string,
    @Query('teamId') teamId?: string,
    @Query('from') from?: string,
    @Query('to') to?: string,
    @Query('verifyStatus') verifyStatus?: VerifyStatus,
  ) {
    return this.locationCheckinService.findAll({ userId, teamId, from, to, verifyStatus });
  }

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR)
  @Patch(':id/verify')
  verify(@Param('id') id: string, @Body() dto: VerifyPhotoDto, @CurrentUser() user: AuthUser) {
    return this.locationCheckinService.verify(id, dto.status, dto.remark, user.id);
  }
}
