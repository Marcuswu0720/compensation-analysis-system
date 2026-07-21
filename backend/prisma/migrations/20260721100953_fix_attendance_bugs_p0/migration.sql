/*
  Warnings:

  - Added the required column `photoData` to the `LocationCheckInPhoto` table without a default value. This is not possible if the table is not empty.

*/
-- AlterEnum
ALTER TYPE "AttendanceStatus" ADD VALUE 'UNCONFIGURED';

-- AlterTable
ALTER TABLE "AttendanceRecord" ADD COLUMN     "clockInLat" DOUBLE PRECISION,
ADD COLUMN     "clockInLng" DOUBLE PRECISION,
ADD COLUMN     "matchedOfficeId" TEXT;

-- AlterTable
-- 已有的历史记录（若有）用空字节占位，因为旧数据的图片文件是存在本地磁盘/旧 uploads 目录的，
-- 迁移后无法自动找回；新上传的记录会走新的数据库存储逻辑，不受影响。
ALTER TABLE "LocationCheckInPhoto" ADD COLUMN     "photoData" BYTEA NOT NULL DEFAULT '\x',
ADD COLUMN     "photoMimeType" TEXT NOT NULL DEFAULT 'image/jpeg';
ALTER TABLE "LocationCheckInPhoto" ALTER COLUMN "photoData" DROP DEFAULT;

-- AddForeignKey
ALTER TABLE "AttendanceRecord" ADD CONSTRAINT "AttendanceRecord_matchedOfficeId_fkey" FOREIGN KEY ("matchedOfficeId") REFERENCES "Office"("id") ON DELETE SET NULL ON UPDATE CASCADE;
