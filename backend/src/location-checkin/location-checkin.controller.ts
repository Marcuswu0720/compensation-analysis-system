import { BadRequestException, Body, Controller, Get, Param, Patch, Post, Query, Res, UploadedFile, UseInterceptors } from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { memoryStorage } from 'multer';
import type { Response } from 'express';
import { Role, VerifyStatus } from '@prisma/client';
import { Roles } from '../common/decorators/roles.decorator';
import { CurrentUser } from '../common/decorators/current-user.decorator';
import { Public } from '../common/decorators/public.decorator';
import { AuthUser } from '../auth/auth.types';
import { LocationCheckinService } from './location-checkin.service';
import { VerifyPhotoDto } from './dto/verify-photo.dto';

@Controller('location-checkin')
export class LocationCheckinController {
  constructor(private locationCheckinService: LocationCheckinService) {}

  @Post()
  @UseInterceptors(
    FileInterceptor('photo', {
      storage: memoryStorage(), // 存数据库而非本地磁盘，避免云端免费实例磁盘不持久（问题反馈 4.2）
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
      photoBuffer: file.buffer,
      mimeType: file.mimetype || 'image/jpeg',
      gpsLat: parseFloat(body.lat),
      gpsLng: parseFloat(body.lng),
      takenAt: body.takenAt,
      businessMetricValue: body.businessMetricValue ? parseInt(body.businessMetricValue, 10) : undefined,
    });
  }

  // 图片以 <img>/<Image> 标签直接加载，浏览器不会带 Authorization 头，所以这里对外公开（与此前本地静态文件
  // 服务的访问控制水平一致——都是靠 UUID 不可猜测，不是新增的安全弱化）
  @Public()
  @Get(':id/photo')
  async getPhoto(@Param('id') id: string, @Res() res: Response) {
    const photo = await this.locationCheckinService.getPhotoBinary(id);
    res.setHeader('Content-Type', photo.photoMimeType || 'image/jpeg');
    res.setHeader('Cache-Control', 'private, max-age=86400');
    // Prisma 的 Bytes 字段返回的是 Uint8Array，Express 的 res.send() 只对真正的 Buffer 实例走原始二进制发送，
    // 否则会被当成普通对象走 JSON 序列化，图片就打不开了，必须显式包一层 Buffer
    res.send(Buffer.from(photo.photoData));
  }

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR)
  @Get('pending')
  findPending() {
    return this.locationCheckinService.findPending();
  }

  // 定位打卡员工本人也可以查看自己的打卡轨迹照片（问题反馈 4.3），非本人则需要小管理者/本地HR权限
  @Get('trajectory')
  findTrajectory(@Query('userId') userId: string, @Query('date') date: string, @CurrentUser() user: AuthUser) {
    const targetUserId = user.role === Role.EMPLOYEE ? user.id : userId;
    return this.locationCheckinService.findTrajectory(targetUserId, date);
  }

  // 同样地，普通员工调用通用列表接口时强制只能看到自己的记录，避免越权拿到他人定位打卡数据
  @Get()
  findAll(
    @Query('userId') userId: string | undefined,
    @Query('teamId') teamId: string | undefined,
    @Query('from') from: string | undefined,
    @Query('to') to: string | undefined,
    @Query('verifyStatus') verifyStatus: VerifyStatus | undefined,
    @CurrentUser() user: AuthUser,
  ) {
    if (user.role === Role.EMPLOYEE) {
      return this.locationCheckinService.findAll({ userId: user.id, from, to, verifyStatus });
    }
    return this.locationCheckinService.findAll({ userId, teamId, from, to, verifyStatus });
  }

  @Roles(Role.LOCAL_MANAGER, Role.LOCAL_HR)
  @Patch(':id/verify')
  verify(@Param('id') id: string, @Body() dto: VerifyPhotoDto, @CurrentUser() user: AuthUser) {
    return this.locationCheckinService.verify(id, dto.status, dto.remark, user.id);
  }
}
