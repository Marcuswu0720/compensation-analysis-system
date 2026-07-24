-- CreateEnum
CREATE TYPE "AnomalyReviewStatus" AS ENUM ('PENDING', 'REVIEWED');

-- AlterEnum
ALTER TYPE "Role" ADD VALUE 'QC_TEAM';

-- AlterTable
ALTER TABLE "TeamAttendanceRuleTemplate" ADD COLUMN     "photoIntervalPreWarnMinutes" INTEGER;

-- CreateTable
CREATE TABLE "LocationCheckinAnomaly" (
    "id" TEXT NOT NULL,
    "photoId" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "intervalMinutes" INTEGER NOT NULL,
    "thresholdMinutes" INTEGER NOT NULL,
    "status" "AnomalyReviewStatus" NOT NULL DEFAULT 'PENDING',
    "reviewNote" TEXT,
    "reviewedById" TEXT,
    "reviewedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "LocationCheckinAnomaly_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Notification" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "message" TEXT NOT NULL,
    "relatedEntityType" TEXT,
    "relatedEntityId" TEXT,
    "isRead" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Notification_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "LocationCheckinAnomaly_photoId_key" ON "LocationCheckinAnomaly"("photoId");

-- CreateIndex
CREATE INDEX "LocationCheckinAnomaly_status_idx" ON "LocationCheckinAnomaly"("status");

-- CreateIndex
CREATE INDEX "LocationCheckinAnomaly_userId_idx" ON "LocationCheckinAnomaly"("userId");

-- CreateIndex
CREATE INDEX "Notification_userId_isRead_idx" ON "Notification"("userId", "isRead");

-- AddForeignKey
ALTER TABLE "LocationCheckinAnomaly" ADD CONSTRAINT "LocationCheckinAnomaly_photoId_fkey" FOREIGN KEY ("photoId") REFERENCES "LocationCheckInPhoto"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LocationCheckinAnomaly" ADD CONSTRAINT "LocationCheckinAnomaly_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LocationCheckinAnomaly" ADD CONSTRAINT "LocationCheckinAnomaly_reviewedById_fkey" FOREIGN KEY ("reviewedById") REFERENCES "User"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Notification" ADD CONSTRAINT "Notification_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
