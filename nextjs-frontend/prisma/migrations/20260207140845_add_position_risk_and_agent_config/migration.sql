-- CreateTable
CREATE TABLE "PositionRisk" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "broker" "BrokerType" NOT NULL,
    "symbol" TEXT NOT NULL,
    "stopLossPrice" DOUBLE PRECISION,
    "takeProfitPrice" DOUBLE PRECISION,
    "isActive" BOOLEAN NOT NULL DEFAULT true,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "PositionRisk_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AgentConfig" (
    "id" TEXT NOT NULL,
    "userId" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "broker" "BrokerType" NOT NULL DEFAULT 'BITGET',
    "maxPositionSizeUsd" DOUBLE PRECISION NOT NULL DEFAULT 100,
    "maxConcurrentPositions" INTEGER NOT NULL DEFAULT 3,
    "dailyLossLimitUsd" DOUBLE PRECISION NOT NULL DEFAULT 500,
    "maxDrawdownPct" DOUBLE PRECISION NOT NULL DEFAULT 10,
    "aggressiveness" DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    "allowedSymbols" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "AgentConfig_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "PositionRisk_userId_broker_symbol_key" ON "PositionRisk"("userId", "broker", "symbol");

-- CreateIndex
CREATE UNIQUE INDEX "AgentConfig_userId_key" ON "AgentConfig"("userId");

-- CreateIndex
CREATE INDEX "Order_userId_status_idx" ON "Order"("userId", "status");

-- AddForeignKey
ALTER TABLE "PositionRisk" ADD CONSTRAINT "PositionRisk_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AgentConfig" ADD CONSTRAINT "AgentConfig_userId_fkey" FOREIGN KEY ("userId") REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE;
