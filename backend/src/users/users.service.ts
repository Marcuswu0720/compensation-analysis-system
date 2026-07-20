import { Injectable } from '@nestjs/common';
import { AuditAction, Role } from '@prisma/client';
import * as bcrypt from 'bcrypt';
import * as XLSX from 'xlsx';
import { PrismaService } from '../prisma/prisma.service';
import { AuditService } from '../common/audit/audit.service';
import { CreateUserDto } from './dto/create-user.dto';
import { UpdateUserDto } from './dto/update-user.dto';

const SELECT_SAFE = {
  id: true,
  employeeNo: true,
  name: true,
  email: true,
  role: true,
  departmentId: true,
  teamId: true,
  managerId: true,
  position: true,
  officeId: true,
  hireDate: true,
  isActive: true,
  createdAt: true,
} as const;

@Injectable()
export class UsersService {
  constructor(
    private prisma: PrismaService,
    private audit: AuditService,
  ) {}

  async create(dto: CreateUserDto, operatorId: string) {
    const passwordHash = await bcrypt.hash(dto.password, 10);
    const { password, ...rest } = dto;
    const user = await this.prisma.user.create({
      data: { ...rest, passwordHash, hireDate: dto.hireDate ? new Date(dto.hireDate) : undefined },
      select: SELECT_SAFE,
    });
    await this.audit.log({
      entityType: 'USER',
      entityId: user.id,
      action: AuditAction.CREATE,
      operatorId,
      detail: { after: user },
    });
    return user;
  }

  findAll(filters: { departmentId?: string; teamId?: string; keyword?: string }) {
    return this.prisma.user.findMany({
      where: {
        departmentId: filters.departmentId,
        teamId: filters.teamId,
        OR: filters.keyword
          ? [
              { name: { contains: filters.keyword, mode: 'insensitive' } },
              { employeeNo: { contains: filters.keyword, mode: 'insensitive' } },
              { email: { contains: filters.keyword, mode: 'insensitive' } },
            ]
          : undefined,
      },
      select: { ...SELECT_SAFE, department: true, team: true },
      orderBy: { createdAt: 'desc' },
    });
  }

  findOne(id: string) {
    return this.prisma.user.findUniqueOrThrow({
      where: { id },
      select: { ...SELECT_SAFE, department: true, team: true, office: true, manager: { select: { id: true, name: true } } },
    });
  }

  async update(id: string, dto: UpdateUserDto, operatorId: string) {
    const before = await this.prisma.user.findUniqueOrThrow({ where: { id }, select: SELECT_SAFE });
    const after = await this.prisma.user.update({
      where: { id },
      data: { ...dto, hireDate: dto.hireDate ? new Date(dto.hireDate) : undefined },
      select: SELECT_SAFE,
    });
    await this.audit.log({
      entityType: 'USER',
      entityId: id,
      action: AuditAction.UPDATE,
      operatorId,
      detail: { before, after },
    });
    return after;
  }

  async setActive(id: string, isActive: boolean, operatorId: string) {
    const after = await this.prisma.user.update({ where: { id }, data: { isActive }, select: SELECT_SAFE });
    await this.audit.log({
      entityType: 'USER',
      entityId: id,
      action: AuditAction.UPDATE,
      operatorId,
      detail: { after, note: isActive ? 'ENABLE' : 'DISABLE' },
    });
    return after;
  }

  // 批量导入（Excel）：列头需为 employeeNo,name,email,password,role,departmentId,teamId,position
  async importFromExcel(buffer: Buffer, operatorId: string) {
    const workbook = XLSX.read(buffer, { type: 'buffer' });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const rows = XLSX.utils.sheet_to_json<Record<string, string>>(sheet);

    const results: { row: number; employeeNo?: string; success: boolean; error?: string }[] = [];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      try {
        const passwordHash = await bcrypt.hash(String(row.password ?? 'Passw0rd!'), 10);
        const user = await this.prisma.user.create({
          data: {
            employeeNo: String(row.employeeNo),
            name: String(row.name),
            email: String(row.email),
            passwordHash,
            role: (row.role as Role) ?? Role.EMPLOYEE,
            departmentId: row.departmentId || undefined,
            teamId: row.teamId || undefined,
            position: row.position || undefined,
          },
          select: { id: true, employeeNo: true },
        });
        results.push({ row: i + 2, employeeNo: user.employeeNo, success: true });
      } catch (e: any) {
        results.push({ row: i + 2, employeeNo: row.employeeNo, success: false, error: e.message });
      }
    }

    await this.audit.log({
      entityType: 'USER',
      entityId: 'BATCH_IMPORT',
      action: AuditAction.CREATE,
      operatorId,
      detail: { total: rows.length, success: results.filter((r) => r.success).length },
    });

    return { total: rows.length, success: results.filter((r) => r.success).length, results };
  }
}
