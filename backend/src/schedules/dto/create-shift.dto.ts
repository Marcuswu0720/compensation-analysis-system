import { IsOptional, IsString, Matches } from 'class-validator';

export class CreateShiftDto {
  @IsString()
  teamId: string;

  @IsString()
  name: string;

  @IsOptional()
  @IsString()
  nameEn?: string;

  @IsString()
  @Matches(/^([01]\d|2[0-3]):[0-5]\d$/)
  startTime: string;

  @IsString()
  @Matches(/^([01]\d|2[0-3]):[0-5]\d$/)
  endTime: string;
}
