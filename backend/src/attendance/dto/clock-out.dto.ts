import { IsLatitude, IsLongitude, IsOptional } from 'class-validator';

export class ClockOutDto {
  @IsOptional()
  @IsLatitude()
  lat?: number;

  @IsOptional()
  @IsLongitude()
  lng?: number;
}
