import { Module } from '@nestjs/common';
import { LocationCheckinService } from './location-checkin.service';
import { LocationCheckinController } from './location-checkin.controller';
import { OfficesModule } from '../offices/offices.module';

@Module({
  imports: [OfficesModule],
  controllers: [LocationCheckinController],
  providers: [LocationCheckinService],
})
export class LocationCheckinModule {}
