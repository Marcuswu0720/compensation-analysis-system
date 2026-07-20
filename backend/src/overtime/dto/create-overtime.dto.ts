import { IsDateString, IsNumber, IsString, Min } from 'class-validator';

export class CreateOvertimeDto {
  @IsDateString()
  date: string;

  @IsNumber()
  @Min(0.5)
  hours: number;

  @IsString()
  reason: string;
}
