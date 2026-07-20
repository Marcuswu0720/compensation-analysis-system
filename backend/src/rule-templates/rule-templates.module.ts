import { Module } from '@nestjs/common';
import { RuleTemplatesService } from './rule-templates.service';
import { RuleTemplatesController } from './rule-templates.controller';

@Module({
  controllers: [RuleTemplatesController],
  providers: [RuleTemplatesService],
})
export class RuleTemplatesModule {}
