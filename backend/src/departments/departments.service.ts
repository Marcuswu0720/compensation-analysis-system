import { Injectable } from '@nestjs/common';
import { AuditAction } from '@prisma/client';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateDepartmentDto } from './dto/create-department.dto';
import { UpdateDepartmentDto } from './dto/update-department.dto';

@Injectable()
export class DepartmentsService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  async create(dto: CreateDepartmentDto, operatorId: string) {
    const dept = await this.prisma.department.create({ data: dto });
    await this.audit.log({
      entityType: 'DEPARTMENT',
      entityId: dept.id,
      action: AuditAction.CREATE,
      operatorId,
      detail: { after: dept },
    });
    return dept;
  }

  findTree() {
    return this.prisma.department.findMany({
      where: { parentId: null },
      include: { children: { include: { children: true } }, leader: { select: { id: true, name: true } } },
    });
  }

  findAll() {
    return this.prisma.department.findMany({
      include: { leader: { select: { id: true, name: true } } },
      orderBy: { createdAt: 'asc' },
    });
  }

  findOne(id: string) {
    return this.prisma.department.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateDepartmentDto, operatorId: string) {
    const before = await this.prisma.department.findUniqueOrThrow({ where: { id } });
    const after = await this.prisma.department.update({ where: { id }, data: dto });
    await this.audit.log({
      entityType: 'DEPARTMENT',
      entityId: id,
      action: AuditAction.UPDATE,
      operatorId,
      detail: { before, after },
    });
    return after;
  }

  async remove(id: string, operatorId: string) {
    const before = await this.prisma.department.findUniqueOrThrow({ where: { id } });
    await this.prisma.department.delete({ where: { id } });
    await this.audit.log({
      entityType: 'DEPARTMENT',
      entityId: id,
      action: AuditAction.DELETE,
      operatorId,
      detail: { before },
    });
    return { success: true };
  }
}
