import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { sendPasswordResetEmail } from '@/lib/email';
import { forgotPasswordLimiter } from '@/lib/rate-limit';
import { randomUUID } from 'crypto';

export async function POST(req: NextRequest) {
  try {
    // Rate limit by IP
    const ip = req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'unknown';
    const limit = await forgotPasswordLimiter.check(ip);
    if (!limit.allowed) {
      return NextResponse.json(
        { error: 'Too many requests. Please try again later.' },
        { status: 429 }
      );
    }

    const { email } = await req.json();

    if (!email || typeof email !== 'string') {
      return NextResponse.json(
        { error: 'Email is required' },
        { status: 400 }
      );
    }

    // Always return 200 to prevent email enumeration
    const user = await prisma.user.findUnique({ where: { email } });

    if (user && user.hashedPassword) {
      const token = randomUUID();
      const expiry = new Date(Date.now() + 60 * 60 * 1000); // 1 hour

      await prisma.user.update({
        where: { id: user.id },
        data: { resetToken: token, resetExpiry: expiry },
      });

      try {
        await sendPasswordResetEmail(email, token);
      } catch (emailError) {
        console.error('Failed to send reset email:', emailError);
      }
    }

    // Anti-enumeration: always return success
    return NextResponse.json({
      message: 'If an account exists with this email, you will receive a password reset link.',
    });
  } catch (error) {
    console.error('Forgot password error:', error);
    return NextResponse.json(
      { error: 'Something went wrong' },
      { status: 500 }
    );
  }
}
