import { IsOptional, IsString } from 'class-validator';

export class CreateLeaveTypeDto {
  @IsString()
  code: string;

  @IsString()
  name: string;

  @IsOptional()
  @IsString()
  nameEn?: string;
}
