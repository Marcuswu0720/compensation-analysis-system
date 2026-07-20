import { IsBoolean, IsEnum, IsInt, IsOptional, IsString, Min } from 'class-validator';
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
}
