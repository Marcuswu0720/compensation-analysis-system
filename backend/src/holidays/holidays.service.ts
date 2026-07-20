import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { CreateHolidayDto } from './dto/create-holiday.dto';

@Injectable()
export class HolidaysService {
  constructor(private prisma: PrismaService) {}

  create(dto: CreateHolidayDto) {
    return this.prisma.holiday.create({ data: { date: new Date(dto.date), name: dto.name, isWorkday: dto.isWorkday ?? false } });
  }

  findAll(year?: string) {
    return this.prisma.holiday.findMany({
      where: year
        ? { date: { gte: new Date(`${year}-01-01`), lt: new Date(`${Number(year) + 1}-01-01`) } }
        : undefined,
      orderBy: { date: 'asc' },
    });
  }

  remove(id: string) {
    return this.prisma.holiday.delete({ where: { id } });
  }
}
