import { Module } from '@nestjs/common';
import { LocationAnomaliesService } from './location-anomalies.service';
import { LocationAnomaliesController } from './location-anomalies.controller';

@Module({
  controllers: [LocationAnomaliesController],
  providers: [LocationAnomaliesService],
})
export class LocationAnomaliesModule {}
