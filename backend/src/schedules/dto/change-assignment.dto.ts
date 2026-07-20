import { IsString } from 'class-validator';

export class ChangeAssignmentDto {
  @IsString()
  newShiftId: string;
}
