import { AttendanceMode, OfficeAssignmentMode, PrismaClient, Role } from '@prisma/client';
import * as bcrypt from 'bcrypt';

const prisma = new PrismaClient();

async function main() {
  const passwordHash = await bcrypt.hash('Passw0rd!', 10);

  // --- 部门 ---
  const hqDept = await prisma.department.create({ data: { name: '总部' } });
  const installmentDept = await prisma.department.create({ data: { name: '分期部', parentId: hqDept.id } });
  const smeDept = await prisma.department.create({ data: { name: 'SME部', parentId: hqDept.id } });
  const supplyChainDept = await prisma.department.create({ data: { name: '供应链部', parentId: hqDept.id } });

  // --- 办公室（尼日利亚场景，含GPS用于最近办公室分配） ---
  const lagosOffice = await prisma.office.create({
    data: { name: 'Lagos Office', address: 'Lagos, Nigeria', gpsLat: 6.5244, gpsLng: 3.3792 },
  });
  const abujaOffice = await prisma.office.create({
    data: { name: 'Abuja Office', address: 'Abuja, Nigeria', gpsLat: 9.0765, gpsLng: 7.3986 },
  });
  const kanoOffice = await prisma.office.create({
    data: { name: 'Kano Office', address: 'Kano, Nigeria', gpsLat: 12.0022, gpsLng: 8.5919 },
  });

  // --- 团队（覆盖三种打卡模式 + 7.1细分场景） ---
  const itTeam = await prisma.team.create({ data: { name: 'IT团队', departmentId: hqDept.id } });
  const kaTeam = await prisma.team.create({ data: { name: '线上收单-KA', departmentId: supplyChainDept.id } });
  const creditReviewTeam = await prisma.team.create({ data: { name: '分期-信审', departmentId: installmentDept.id } });
  const fieldCollectionTeam = await prisma.team.create({ data: { name: '分期-催收-地催团队', departmentId: installmentDept.id } });
  const smeFieldCollectionTeam = await prisma.team.create({ data: { name: 'SME-催收-地推催收', departmentId: smeDept.id } });
  const smeBdTeam = await prisma.team.create({ data: { name: 'SME-BD-码牌团队', departmentId: smeDept.id } });

  await prisma.teamAttendanceModeConfig.createMany({
    data: [
      { teamId: itTeam.id, mode: AttendanceMode.OFFICE },
      { teamId: kaTeam.id, mode: AttendanceMode.SHIFT },
      { teamId: creditReviewTeam.id, mode: AttendanceMode.SHIFT },
      { teamId: fieldCollectionTeam.id, mode: AttendanceMode.OFFICE },
      { teamId: smeFieldCollectionTeam.id, mode: AttendanceMode.LOCATION },
      { teamId: smeBdTeam.id, mode: AttendanceMode.LOCATION },
    ],
  });

  await prisma.officeAttendanceRule.createMany({
    data: [
      { teamId: itTeam.id, startTime: '09:00', endTime: '18:00', lateGraceMinutes: 10, earlyGraceMinutes: 0 },
      // 地催团队打卡模式为 OFFICE + NEAREST_AUTO 分配，同样需要上下班时间/迟到宽限才能判定状态，
      // 此前遗漏导致该团队员工打卡永远显示"未配置考勤规则"（问题反馈 2.3）
      { teamId: fieldCollectionTeam.id, startTime: '09:00', endTime: '18:00', lateGraceMinutes: 15, earlyGraceMinutes: 0 },
    ],
  });
  // IT团队关联 Lagos 办公室，打卡时校验地理围栏范围（问题反馈 1.1）
  await prisma.officeAttendanceRule.update({
    where: { teamId: itTeam.id },
    data: { offices: { connect: [{ id: lagosOffice.id }] } },
  });

  await prisma.shift.createMany({
    data: [
      { teamId: kaTeam.id, name: '早班', nameEn: 'Morning shift', startTime: '08:00', endTime: '16:00' },
      { teamId: kaTeam.id, name: '晚班', nameEn: 'Evening shift', startTime: '14:00', endTime: '22:00' },
      { teamId: creditReviewTeam.id, name: '早班', nameEn: 'Morning shift', startTime: '09:00', endTime: '17:00' },
    ],
  });

  // 7.1 细分规则模板
  await prisma.teamAttendanceRuleTemplate.createMany({
    data: [
      {
        teamId: fieldCollectionTeam.id,
        requiresClockIn: true,
        requiresClockOut: false, // 只打上班卡，下班在客户家不打卡
        requiresPhoto: false,
        requiresBusinessMetric: false,
        officeAssignmentMode: OfficeAssignmentMode.NEAREST_AUTO,
      },
      {
        teamId: smeFieldCollectionTeam.id,
        requiresClockIn: false,
        requiresClockOut: false,
        requiresPhoto: true, // 上传拜访商户照片替代打卡
        photoIntervalThresholdMinutes: 180,
        requiresBusinessMetric: false,
        officeAssignmentMode: OfficeAssignmentMode.NONE,
      },
      {
        teamId: smeBdTeam.id,
        requiresClockIn: true,
        requiresClockOut: true,
        requiresPhoto: true,
        requiresBusinessMetric: true,
        businessMetricThreshold: 8, // 超过8家商户才算出勤
        businessMetricSource: 'MANUAL',
        officeAssignmentMode: OfficeAssignmentMode.FIXED, // 拍照打卡校验是否在有效范围内（问题反馈 2.5）
      },
    ],
  });
  // 码牌团队的有效打卡范围关联 Lagos 办公室（问题反馈 2.5，仅作标记不阻断打卡）
  await prisma.teamAttendanceRuleTemplate.update({
    where: { teamId: smeBdTeam.id },
    data: { offices: { connect: [{ id: lagosOffice.id }] } },
  });

  // --- 请假类型（10.3 可配置枚举） ---
  await prisma.leaveTypeConfig.createMany({
    data: [
      { code: 'PERSONAL', name: '事假', nameEn: 'Personal Leave' },
      { code: 'SICK', name: '病假', nameEn: 'Sick Leave' },
      { code: 'ANNUAL', name: '年假', nameEn: 'Annual Leave' },
      { code: 'MARRIAGE', name: '婚假', nameEn: 'Marriage Leave' },
      { code: 'MATERNITY', name: '产假', nameEn: 'Maternity Leave' },
    ],
  });

  // --- 用户：覆盖4类角色 + 3种打卡模式员工 ---
  const hqAdmin = await prisma.user.create({
    data: {
      employeeNo: 'HQ001',
      name: 'HQ Admin',
      email: 'hq.admin@example.com',
      passwordHash,
      role: Role.HQ,
    },
  });

  const localHr = await prisma.user.create({
    data: {
      employeeNo: 'HR001',
      name: 'Ngozi (Local HR)',
      email: 'hr@example.com',
      passwordHash,
      role: Role.LOCAL_HR,
      departmentId: hqDept.id,
      officeId: lagosOffice.id,
    },
  });

  await prisma.user.create({
    data: {
      employeeNo: 'QC001',
      name: 'Bola (QC Team)',
      email: 'qc@example.com',
      passwordHash,
      role: Role.QC_TEAM,
      departmentId: hqDept.id,
    },
  });

  const localManager = await prisma.user.create({
    data: {
      employeeNo: 'MGR001',
      name: 'Chidi (Local Manager)',
      email: 'manager@example.com',
      passwordHash,
      role: Role.LOCAL_MANAGER,
      departmentId: smeDept.id,
      teamId: smeBdTeam.id,
      officeId: lagosOffice.id,
    },
  });

  // 码牌团队负责人是 Chidi 本人：定位打卡审核不能自审自批，需交由本地HR审核（问题反馈 2.1）
  await prisma.team.update({ where: { id: smeBdTeam.id }, data: { leaderId: localManager.id } });

  await prisma.user.create({
    data: {
      employeeNo: 'EMP001',
      name: 'Amaka (Office)',
      email: 'amaka@example.com',
      passwordHash,
      role: Role.EMPLOYEE,
      departmentId: hqDept.id,
      teamId: itTeam.id,
      officeId: lagosOffice.id,
      hireDate: new Date('2024-01-15'),
    },
  });

  await prisma.user.create({
    data: {
      employeeNo: 'EMP002',
      name: 'Emeka (Shift)',
      email: 'emeka@example.com',
      passwordHash,
      role: Role.EMPLOYEE,
      departmentId: supplyChainDept.id,
      teamId: kaTeam.id,
      officeId: abujaOffice.id,
      hireDate: new Date('2024-03-01'),
    },
  });

  await prisma.user.create({
    data: {
      employeeNo: 'EMP003',
      name: 'Ifeoma (Field Collection)',
      email: 'ifeoma@example.com',
      passwordHash,
      role: Role.EMPLOYEE,
      departmentId: installmentDept.id,
      teamId: fieldCollectionTeam.id,
      officeId: kanoOffice.id,
      hireDate: new Date('2024-05-20'),
    },
  });

  await prisma.user.create({
    data: {
      employeeNo: 'EMP004',
      name: 'Tunde (SME BD)',
      email: 'tunde@example.com',
      passwordHash,
      role: Role.EMPLOYEE,
      departmentId: smeDept.id,
      teamId: smeBdTeam.id,
      officeId: lagosOffice.id,
      hireDate: new Date('2024-06-10'),
    },
  });

  console.log('Seed complete. Demo accounts (password: Passw0rd!):');
  console.log('  hq.admin@example.com   (HQ, 只读)');
  console.log('  hr@example.com         (LOCAL_HR)');
  console.log('  qc@example.com         (QC_TEAM)');
  console.log('  manager@example.com    (LOCAL_MANAGER)');
  console.log('  amaka@example.com      (EMPLOYEE, 办公室打卡)');
  console.log('  emeka@example.com      (EMPLOYEE, 排班打卡)');
  console.log('  ifeoma@example.com     (EMPLOYEE, 地催-办公室打卡最近分配)');
  console.log('  tunde@example.com      (EMPLOYEE, SME-BD 码牌团队-定位打卡)');
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
