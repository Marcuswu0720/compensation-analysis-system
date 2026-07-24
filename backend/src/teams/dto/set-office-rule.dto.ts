import { IsArray, IsInt, IsOptional, IsString, Matches, Min } from 'class-validator';

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

  // 关联办公室（问题反馈 1.1）：留空表示不做地理围栏校验，沿用原行为
  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  officeIds?: string[];
}
