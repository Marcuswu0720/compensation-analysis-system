import { PartialType, OmitType } from '@nestjs/mapped-types';
import { CreateShiftDto } from './create-shift.dto';

export class UpdateShiftDto extends PartialType(OmitType(CreateShiftDto, ['teamId'] as const)) {}
