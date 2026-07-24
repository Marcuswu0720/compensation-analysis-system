-- AlterTable
ALTER TABLE "Office" ADD COLUMN     "allowedRadiusMeters" INTEGER NOT NULL DEFAULT 300;

-- CreateTable
CREATE TABLE "_OfficeRuleOffices" (
    "A" TEXT NOT NULL,
    "B" TEXT NOT NULL,

    CONSTRAINT "_OfficeRuleOffices_AB_pkey" PRIMARY KEY ("A","B")
);

-- CreateIndex
CREATE INDEX "_OfficeRuleOffices_B_index" ON "_OfficeRuleOffices"("B");

-- AddForeignKey
ALTER TABLE "_OfficeRuleOffices" ADD CONSTRAINT "_OfficeRuleOffices_A_fkey" FOREIGN KEY ("A") REFERENCES "Office"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_OfficeRuleOffices" ADD CONSTRAINT "_OfficeRuleOffices_B_fkey" FOREIGN KEY ("B") REFERENCES "OfficeAttendanceRule"("id") ON DELETE CASCADE ON UPDATE CASCADE;
