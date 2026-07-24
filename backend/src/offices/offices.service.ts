import { Injectable } from '@nestjs/common';
import type { Office } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { CreateOfficeDto } from './dto/create-office.dto';
import { UpdateOfficeDto } from './dto/update-office.dto';

@Injectable()
export class OfficesService {
  constructor(private prisma: PrismaService) {}

  create(dto: CreateOfficeDto) {
    return this.prisma.office.create({ data: dto });
  }

  findAll() {
    return this.prisma.office.findMany({ orderBy: { createdAt: 'asc' } });
  }

  findOne(id: string) {
    return this.prisma.office.findUniqueOrThrow({ where: { id } });
  }

  update(id: string, dto: UpdateOfficeDto) {
    return this.prisma.office.update({ where: { id }, data: dto });
  }

  remove(id: string) {
    return this.prisma.office.update({ where: { id }, data: { isActive: false } });
  }

  // 定位打卡地催团队：出勤日到最近的（系统自动分配）办公室打上班卡
  async findNearest(lat: number, lng: number) {
    const offices = await this.prisma.office.findMany({
      where: { isActive: true, gpsLat: { not: null }, gpsLng: { not: null } },
    });
    let nearest: (typeof offices)[number] | null = null;
    let minDist = Infinity;
    for (const office of offices) {
      const dist = haversine(lat, lng, office.gpsLat!, office.gpsLng!);
      if (dist < minDist) {
        minDist = dist;
        nearest = office;
      }
    }
    return nearest ? { office: nearest, distanceKm: minDist } : null;
  }

  // 团队关联办公室后的打卡范围校验（问题反馈 1.1）：只要落在任一关联办公室的允许半径内即视为合规
  findNearestWithin(lat: number, lng: number, offices: Office[]): { office: Office; distanceMeters: number } | null {
    let nearest: { office: Office; distanceMeters: number } | null = null;
    for (const office of offices) {
      if (office.gpsLat == null || office.gpsLng == null) continue;
      const distanceMeters = haversine(lat, lng, office.gpsLat, office.gpsLng) * 1000;
      if (distanceMeters <= office.allowedRadiusMeters && (!nearest || distanceMeters < nearest.distanceMeters)) {
        nearest = { office, distanceMeters };
      }
    }
    return nearest;
  }
}

function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
