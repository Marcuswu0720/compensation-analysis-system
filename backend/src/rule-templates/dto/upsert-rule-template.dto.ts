import { IsArray, IsBoolean, IsEnum, IsInt, IsOptional, IsString, Min } from 'class-validator';
import { OfficeAssignmentMode } from '@prisma/client';

export class UpsertRuleTemplateDto {
  @IsBoolean()
  requiresClockIn: boolean;

  @IsBoolean()
  requiresClockOut: boolean;

  @IsBoolean()
  requiresPhoto: boolean;

  @IsOptional()
  @IsInt()
  @Min(1)
  photoIntervalThresholdMinutes?: number;

  @IsBoolean()
  requiresBusinessMetric: boolean;

  @IsOptional()
  @IsInt()
  @Min(1)
  businessMetricThreshold?: number;

  @IsOptional()
  @IsString()
  businessMetricSource?: string;

  @IsEnum(OfficeAssignmentMode)
  officeAssignmentMode: OfficeAssignmentMode;

  // officeAssignmentMode 为 FIXED 时，关联的有效打卡地点（问题反馈 2.5）
  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  officeIds?: string[];
}
