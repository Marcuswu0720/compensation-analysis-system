import { IsEnum } from 'class-validator';
import { AttendanceMode } from '@prisma/client';

export class SetModeConfigDto {
  @IsEnum(AttendanceMode)
  mode: AttendanceMode;
}
