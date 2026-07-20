import { PartialType } from '@nestjs/mapped-types';
import { CreateOfficeDto } from './create-office.dto';
import { IsBoolean, IsOptional } from 'class-validator';

export class UpdateOfficeDto extends PartialType(CreateOfficeDto) {
  @IsOptional()
  @IsBoolean()
  isActive?: boolean;
}
