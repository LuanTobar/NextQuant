import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getStripe } from '@/lib/stripe';
import type Stripe from 'stripe';

export async function POST(req: NextRequest) {
  try {
    const stripe = getStripe();
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET || '';
    const body = await req.text();
    const sig = req.headers.get('stripe-signature');

    if (!sig) {
      return NextResponse.json({ error: 'Missing signature' }, { status: 400 });
    }

    let event: Stripe.Event;
    try {
      event = stripe.webhooks.constructEvent(body, sig, webhookSecret);
    } catch (err) {
      console.error('Webhook signature verification failed:', err);
      return NextResponse.json({ error: 'Invalid signature' }, { status: 400 });
    }

    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session;
        const userId = session.metadata?.userId;
        if (userId && session.subscription) {
          await prisma.user.update({
            where: { id: userId },
            data: {
              plan: 'PRO',
              subscriptionId: session.subscription as string,
              subscriptionStatus: 'active',
            },
          });
        }
        break;
      }

      case 'customer.subscription.updated': {
        const sub = event.data.object as Stripe.Subscription;
        const customer = await stripe.customers.retrieve(sub.customer as string);
        if ('metadata' in customer && customer.metadata?.userId) {
          const status = sub.status;
          await prisma.user.update({
            where: { id: customer.metadata.userId },
            data: {
              subscriptionStatus: status,
              plan: status === 'active' ? 'PRO' : 'FREE',
            },
          });
        }
        break;
      }

      case 'customer.subscription.deleted': {
        const sub = event.data.object as Stripe.Subscription;
        const customer = await stripe.customers.retrieve(sub.customer as string);
        if ('metadata' in customer && customer.metadata?.userId) {
          // Grant 7-day grace period — plan stays PRO, checkTradeAccess() does lazy downgrade
          await prisma.user.update({
            where: { id: customer.metadata.userId },
            data: {
              subscriptionStatus: 'canceled',
              gracePeriodEnd: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000),
            },
          });
        }
        break;
      }

      case 'invoice.payment_failed': {
        const invoice = event.data.object as Stripe.Invoice;
        if (invoice.customer) {
          const customer = await stripe.customers.retrieve(invoice.customer as string);
          if ('metadata' in customer && customer.metadata?.userId) {
            await prisma.user.update({
              where: { id: customer.metadata.userId },
              data: { subscriptionStatus: 'past_due' },
            });
          }
        }
        break;
      }
    }

    return NextResponse.json({ received: true });
  } catch (error) {
    console.error('Webhook error:', error);
    return NextResponse.json({ error: 'Webhook processing failed' }, { status: 500 });
  }
}
