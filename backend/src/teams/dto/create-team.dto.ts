import { IsOptional, IsString } from 'class-validator';

export class CreateTeamDto {
  @IsString()
  name: string;

  @IsString()
  departmentId: string;

  @IsOptional()
  @IsString()
  leaderId?: string;
}
