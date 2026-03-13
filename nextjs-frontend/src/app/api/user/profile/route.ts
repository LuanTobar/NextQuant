import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { sendVerificationEmail } from '@/lib/email';
import { randomUUID } from 'crypto';

export async function PUT(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { name, email } = await req.json();

    if (!name || !email) {
      return NextResponse.json({ error: 'Name and email are required' }, { status: 400 });
    }

    const currentUser = await prisma.user.findUnique({
      where: { id: session.user.id },
    });

    if (!currentUser) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Check if email is changing
    const emailChanged = email !== currentUser.email;

    if (emailChanged) {
      // Check if new email is taken
      const existing = await prisma.user.findUnique({ where: { email } });
      if (existing) {
        return NextResponse.json(
          { error: 'This email is already in use' },
          { status: 409 }
        );
      }
    }

    const updateData: Record<string, unknown> = { name };

    if (emailChanged) {
      const token = randomUUID();
      updateData.email = email;
      updateData.emailVerified = false;
      updateData.verificationToken = token;
      updateData.verificationExpiry = new Date(Date.now() + 24 * 60 * 60 * 1000);

      try {
        await sendVerificationEmail(email, token);
      } catch (e) {
        console.error('Failed to send verification email:', e);
      }
    }

    const updated = await prisma.user.update({
      where: { id: session.user.id },
      data: updateData,
      select: { id: true, name: true, email: true, emailVerified: true },
    });

    return NextResponse.json({
      ...updated,
      emailChanged,
    });
  } catch (error) {
    console.error('Profile update error:', error);
    return NextResponse.json(
      { error: 'Something went wrong' },
      { status: 500 }
    );
  }
}
