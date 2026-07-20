import { ArrayMinSize, IsArray, IsDateString, IsEnum, IsOptional, IsString } from 'class-validator';
import { SpecialEventType } from '@prisma/client';

export class CreateSpecialEventDto {
  @IsEnum(SpecialEventType)
  type: SpecialEventType;

  @IsArray()
  @ArrayMinSize(1)
  @IsString({ each: true })
  affectedOfficeIds: string[];

  @IsDateString()
  startTime: string;

  @IsDateString()
  endTime: string;

  @IsOptional()
  @IsString()
  remark?: string;
}
