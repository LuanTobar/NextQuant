import { Prisma } from '@prisma/client';
import { prisma } from './prisma';

interface AuditLogParams {
  userId: string;
  action: string;
  resource?: string;
  details?: Prisma.InputJsonValue;
  ipAddress?: string;
}

/**
 * Log an audit event. Fire-and-forget (non-blocking).
 */
export function logAudit(params: AuditLogParams) {
  prisma.auditLog
    .create({
      data: {
        userId: params.userId,
        action: params.action,
        resource: params.resource,
        details: params.details ? params.details : undefined,
        ipAddress: params.ipAddress,
      },
    })
    .catch((err) => {
      console.error('Audit log failed:', err);
    });
}
