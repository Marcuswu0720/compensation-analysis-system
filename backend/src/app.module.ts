import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ScheduleModule } from '@nestjs/schedule';
import { APP_GUARD } from '@nestjs/core';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { PrismaModule } from './prisma/prisma.module';
import { AuditModule } from './common/audit/audit.module';
import { JwtAuthGuard } from './common/guards/jwt-auth.guard';
import { RolesGuard } from './common/guards/roles.guard';
import { AuthModule } from './auth/auth.module';
import { UsersModule } from './users/users.module';
import { DepartmentsModule } from './departments/departments.module';
import { TeamsModule } from './teams/teams.module';
import { OfficesModule } from './offices/offices.module';
import { AttendanceModule } from './attendance/attendance.module';
import { SpecialEventsModule } from './special-events/special-events.module';
import { SchedulesModule } from './schedules/schedules.module';
import { LocationCheckinModule } from './location-checkin/location-checkin.module';
import { RuleTemplatesModule } from './rule-templates/rule-templates.module';
import { LeaveModule } from './leave/leave.module';
import { OvertimeModule } from './overtime/overtime.module';
import { ReportsModule } from './reports/reports.module';
import { HolidaysModule } from './holidays/holidays.module';
import { NotificationsModule } from './notifications/notifications.module';
import { LocationAnomaliesModule } from './location-anomalies/location-anomalies.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    ScheduleModule.forRoot(),
    PrismaModule,
    AuditModule,
    AuthModule,
    UsersModule,
    DepartmentsModule,
    TeamsModule,
    OfficesModule,
    AttendanceModule,
    SpecialEventsModule,
    SchedulesModule,
    LocationCheckinModule,
    RuleTemplatesModule,
    LeaveModule,
    OvertimeModule,
    ReportsModule,
    HolidaysModule,
    NotificationsModule,
    LocationAnomaliesModule,
  ],
  controllers: [AppController],
  providers: [
    AppService,
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_GUARD, useClass: RolesGuard },
  ],
})
export class AppModule {}
