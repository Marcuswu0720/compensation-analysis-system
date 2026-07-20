/*
  Warnings:

  - You are about to drop the column `type` on the `LeaveApplication` table. All the data in the column will be lost.
  - Added the required column `typeId` to the `LeaveApplication` table without a default value. This is not possible if the table is not empty.

*/
-- AlterTable
ALTER TABLE "LeaveApplication" DROP COLUMN "type",
ADD COLUMN     "typeId" TEXT NOT NULL;

-- DropEnum
DROP TYPE "LeaveType";

-- CreateTable
CREATE TABLE "OfficeAttendanceRule" (
    "id" TEXT NOT NULL,
    "teamId" TEXT NOT NULL,
    "startTime" TEXT NOT NULL,
    "endTime" TEXT NOT NULL,
    "lateGraceMinutes" INTEGER NOT NULL DEFAULT 0,
    "earlyGraceMinutes" INTEGER NOT NULL DEFAULT 0,
    "updatedBy" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "OfficeAttendanceRule_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "LeaveTypeConfig" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "isActive" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "LeaveTypeConfig_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "OfficeAttendanceRule_teamId_key" ON "OfficeAttendanceRule"("teamId");

-- CreateIndex
CREATE UNIQUE INDEX "LeaveTypeConfig_code_key" ON "LeaveTypeConfig"("code");

-- AddForeignKey
ALTER TABLE "OfficeAttendanceRule" ADD CONSTRAINT "OfficeAttendanceRule_teamId_fkey" FOREIGN KEY ("teamId") REFERENCES "Team"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "LeaveApplication" ADD CONSTRAINT "LeaveApplication_typeId_fkey" FOREIGN KEY ("typeId") REFERENCES "LeaveTypeConfig"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
