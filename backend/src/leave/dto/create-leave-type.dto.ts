import { IsString } from 'class-validator';

export class CreateLeaveTypeDto {
  @IsString()
  code: string;

  @IsString()
  name: string;
}
