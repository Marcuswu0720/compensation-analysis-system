import { IsInt, IsString, Matches, Min } from 'class-validator';

export class SetOfficeRuleDto {
  @IsString()
  @Matches(/^([01]\d|2[0-3]):[0-5]\d$/)
  startTime: string;

  @IsString()
  @Matches(/^([01]\d|2[0-3]):[0-5]\d$/)
  endTime: string;

  @IsInt()
  @Min(0)
  lateGraceMinutes: number;

  @IsInt()
  @Min(0)
  earlyGraceMinutes: number;
}
