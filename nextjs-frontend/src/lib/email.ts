import { Resend } from 'resend';

let _resend: Resend | null = null;
function getResend(): Resend {
  if (!_resend) {
    _resend = new Resend(process.env.RESEND_API_KEY || 'dummy_key');
  }
  return _resend;
}

export async function sendVerificationEmail(email: string, token: string) {
  const FROM_EMAIL = process.env.FROM_EMAIL || 'NexQuant <noreply@nexquant.app>';
  const APP_URL = process.env.NEXTAUTH_URL || 'http://localhost:3005';
  const verifyUrl = `${APP_URL}/api/auth/verify-email?token=${token}`;

  await getResend().emails.send({
    from: FROM_EMAIL,
    to: email,
    subject: 'Verify your NexQuant account',
    html: `
      <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #0a0e17; color: #e5e7eb; padding: 40px 24px; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 32px;">
          <div style="display: inline-block; background: #6366f1; color: white; font-weight: bold; font-size: 18px; width: 48px; height: 48px; line-height: 48px; border-radius: 12px;">NQ</div>
          <h1 style="color: #e5e7eb; margin-top: 16px; font-size: 24px;">Verify your email</h1>
        </div>
        <p style="color: #9ca3af; line-height: 1.6;">Click the button below to verify your email address and activate your NexQuant account.</p>
        <div style="text-align: center; margin: 32px 0;">
          <a href="${verifyUrl}" style="display: inline-block; background: #6366f1; color: white; text-decoration: none; padding: 12px 32px; border-radius: 8px; font-weight: 600; font-size: 14px;">Verify Email</a>
        </div>
        <p style="color: #6b7280; font-size: 12px;">This link expires in 24 hours. If you didn't create an account, you can safely ignore this email.</p>
      </div>
    `,
  });
}

export async function sendPasswordResetEmail(email: string, token: string) {
  const FROM_EMAIL = process.env.FROM_EMAIL || 'NexQuant <noreply@nexquant.app>';
  const APP_URL = process.env.NEXTAUTH_URL || 'http://localhost:3005';
  const resetUrl = `${APP_URL}/auth/reset-password?token=${token}`;

  await getResend().emails.send({
    from: FROM_EMAIL,
    to: email,
    subject: 'Reset your NexQuant password',
    html: `
      <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; background: #0a0e17; color: #e5e7eb; padding: 40px 24px; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 32px;">
          <div style="display: inline-block; background: #6366f1; color: white; font-weight: bold; font-size: 18px; width: 48px; height: 48px; line-height: 48px; border-radius: 12px;">NQ</div>
          <h1 style="color: #e5e7eb; margin-top: 16px; font-size: 24px;">Reset your password</h1>
        </div>
        <p style="color: #9ca3af; line-height: 1.6;">Click the button below to set a new password for your NexQuant account.</p>
        <div style="text-align: center; margin: 32px 0;">
          <a href="${resetUrl}" style="display: inline-block; background: #6366f1; color: white; text-decoration: none; padding: 12px 32px; border-radius: 8px; font-weight: 600; font-size: 14px;">Reset Password</a>
        </div>
        <p style="color: #6b7280; font-size: 12px;">This link expires in 1 hour. If you didn't request a password reset, you can safely ignore this email.</p>
      </div>
    `,
  });
}
