import { Module } from '@nestjs/common';
import { SpecialEventsService } from './special-events.service';
import { SpecialEventsController } from './special-events.controller';

@Module({
  controllers: [SpecialEventsController],
  providers: [SpecialEventsService],
})
export class SpecialEventsModule {}
