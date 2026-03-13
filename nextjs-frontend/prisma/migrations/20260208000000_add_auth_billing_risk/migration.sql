-- Add email verification, password reset, onboarding, billing, and risk profile columns
ALTER TABLE "User"
  ADD COLUMN IF NOT EXISTS "emailVerified" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS "verificationToken" TEXT,
  ADD COLUMN IF NOT EXISTS "verificationExpiry" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "resetToken" TEXT,
  ADD COLUMN IF NOT EXISTS "resetExpiry" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "onboardingCompleted" BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS "stripeCustomerId" TEXT,
  ADD COLUMN IF NOT EXISTS "subscriptionId" TEXT,
  ADD COLUMN IF NOT EXISTS "subscriptionStatus" TEXT,
  ADD COLUMN IF NOT EXISTS "gracePeriodEnd" TIMESTAMP(3);

-- Unique index on stripeCustomerId
CREATE UNIQUE INDEX IF NOT EXISTS "User_stripeCustomerId_key" ON "User"("stripeCustomerId");

-- RiskProfile table (Sprint 1.5)
CREATE TABLE IF NOT EXISTS "RiskProfile" (
  "id" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "investmentHorizon" TEXT NOT NULL,
  "riskTolerance" TEXT NOT NULL,
  "experienceLevel" TEXT NOT NULL,
  "incomeStability" TEXT NOT NULL,
  "lossCapacity" TEXT NOT NULL,
  "primaryGoal" TEXT NOT NULL,
  "riskScore" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  "riskCategory" TEXT NOT NULL DEFAULT 'MODERATE',
  "maxPositionSizeUsd" DOUBLE PRECISION NOT NULL DEFAULT 150,
  "maxConcurrentPositions" INTEGER NOT NULL DEFAULT 3,
  "dailyLossLimitUsd" DOUBLE PRECISION NOT NULL DEFAULT 400,
  "maxDrawdownPct" DOUBLE PRECISION NOT NULL DEFAULT 12,
  "aggressiveness" DOUBLE PRECISION NOT NULL DEFAULT 0.45,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "RiskProfile_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "RiskProfile_userId_key" UNIQUE ("userId"),
  CONSTRAINT "RiskProfile_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- AuditLog table (Sprint 2.5)
CREATE TABLE IF NOT EXISTS "AuditLog" (
  "id" TEXT NOT NULL,
  "userId" TEXT NOT NULL,
  "action" TEXT NOT NULL,
  "resource" TEXT,
  "details" JSONB,
  "ipAddress" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "AuditLog_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "AuditLog_userId_createdAt_idx" ON "AuditLog"("userId", "createdAt");
CREATE INDEX IF NOT EXISTS "AuditLog_action_idx" ON "AuditLog"("action");
