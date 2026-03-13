-- CreateTable
CREATE TABLE "ClaudeDecision" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "mlSignal" JSONB NOT NULL,
    "claudeAnalysis" JSONB NOT NULL,
    "recommendation" TEXT NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "expectedReturn" DOUBLE PRECISION NOT NULL,
    "expectedPnl" DOUBLE PRECISION NOT NULL,
    "riskRewardRatio" DOUBLE PRECISION NOT NULL,
    "adjustedSize" DOUBLE PRECISION,
    "entryPrice" DOUBLE PRECISION,
    "exitPrice" DOUBLE PRECISION,
    "actualPnl" DOUBLE PRECISION,
    "outcome" TEXT,
    "executionStatus" TEXT NOT NULL,
    "latencyMs" INTEGER NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "closedAt" TIMESTAMP(3),

    CONSTRAINT "ClaudeDecision_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ClaudeDecision_userId_createdAt_idx" ON "ClaudeDecision"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "ClaudeDecision_userId_symbol_idx" ON "ClaudeDecision"("userId", "symbol");

-- CreateIndex
CREATE INDEX "ClaudeDecision_symbol_outcome_idx" ON "ClaudeDecision"("symbol", "outcome");

-- AddForeignKey
ALTER TABLE "ClaudeDecision" ADD CONSTRAINT "ClaudeDecision_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
