import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET(req: NextRequest) {
  try {
    const token = req.nextUrl.searchParams.get('token');

    if (!token) {
      return NextResponse.redirect(
        new URL('/auth/login?error=invalid-token', req.url)
      );
    }

    const user = await prisma.user.findFirst({
      where: {
        verificationToken: token,
        verificationExpiry: { gt: new Date() },
      },
    });

    if (!user) {
      return NextResponse.redirect(
        new URL('/auth/login?error=expired-token', req.url)
      );
    }

    await prisma.user.update({
      where: { id: user.id },
      data: {
        emailVerified: true,
        verificationToken: null,
        verificationExpiry: null,
      },
    });

    return NextResponse.redirect(
      new URL('/auth/login?verified=true', req.url)
    );
  } catch (error) {
    console.error('Verify email error:', error);
    return NextResponse.redirect(
      new URL('/auth/login?error=verification-failed', req.url)
    );
  }
}
