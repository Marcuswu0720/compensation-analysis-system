import { ArrayMinSize, IsArray, IsDateString, IsInt, IsOptional, IsString, Max, Min } from 'class-validator';

export class BatchGenerateDto {
  @IsArray()
  @ArrayMinSize(1)
  @IsString({ each: true })
  userIds: string[];

  @IsString()
  shiftId: string;

  @IsDateString()
  dateFrom: string;

  @IsDateString()
  dateTo: string;

  // 0=周日...6=周六，不传则每天都排
  @IsOptional()
  @IsArray()
  @IsInt({ each: true })
  @Min(0, { each: true })
  @Max(6, { each: true })
  daysOfWeek?: number[];
}
