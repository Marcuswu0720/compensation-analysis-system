-- AlterTable
ALTER TABLE "LocationCheckInPhoto" ADD COLUMN     "isWithinRange" BOOLEAN;

-- CreateTable
CREATE TABLE "_RuleTemplateOffices" (
    "A" TEXT NOT NULL,
    "B" TEXT NOT NULL,

    CONSTRAINT "_RuleTemplateOffices_AB_pkey" PRIMARY KEY ("A","B")
);

-- CreateIndex
CREATE INDEX "_RuleTemplateOffices_B_index" ON "_RuleTemplateOffices"("B");

-- AddForeignKey
ALTER TABLE "_RuleTemplateOffices" ADD CONSTRAINT "_RuleTemplateOffices_A_fkey" FOREIGN KEY ("A") REFERENCES "Office"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "_RuleTemplateOffices" ADD CONSTRAINT "_RuleTemplateOffices_B_fkey" FOREIGN KEY ("B") REFERENCES "TeamAttendanceRuleTemplate"("id") ON DELETE CASCADE ON UPDATE CASCADE;
