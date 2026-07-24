import { IsOptional, IsString } from 'class-validator';

export class ReviewAnomalyDto {
  @IsOptional()
  @IsString()
  reviewNote?: string;
}
