import { IsLatitude, IsLongitude, IsOptional } from 'class-validator';

export class ClockInDto {
  @IsOptional()
  @IsLatitude()
  lat?: number;

  @IsOptional()
  @IsLongitude()
  lng?: number;
}
