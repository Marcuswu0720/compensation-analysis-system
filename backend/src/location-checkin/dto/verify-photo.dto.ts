import { IsEnum, IsOptional, IsString } from 'class-validator';
import { VerifyStatus } from '@prisma/client';

export class VerifyPhotoDto {
  @IsEnum(VerifyStatus)
  status: VerifyStatus;

  @IsOptional()
  @IsString()
  remark?: string;
}
