import { IsDateString, IsOptional, IsString } from 'class-validator';

export class CreateLeaveApplicationDto {
  @IsString()
  typeId: string;

  @IsDateString()
  startTime: string;

  @IsDateString()
  endTime: string;

  @IsString()
  reason: string;

  @IsOptional()
  @IsString()
  attachmentUrl?: string;
}
