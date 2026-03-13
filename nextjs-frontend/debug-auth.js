const bcrypt = require('bcryptjs');
const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function test() {
  const users = await prisma.user.findMany({ select: { email: true, hashedPassword: true } });
  for (const u of users) {
    const testPw1 = await bcrypt.compare('nexquant123', u.hashedPassword || '');
    const testPw2 = await bcrypt.compare('test1234', u.hashedPassword || '');
    console.log(u.email, '| nexquant123:', testPw1, '| test1234:', testPw2);
  }

  // Reset both passwords
  const hash1 = await bcrypt.hash('nexquant123', 12);
  const hash2 = await bcrypt.hash('test1234', 12);

  await prisma.user.update({ where: { email: 'lucho@nexquant.dev' }, data: { hashedPassword: hash1 } });
  await prisma.user.update({ where: { email: 'test@nexquant.dev' }, data: { hashedPassword: hash2 } });

  console.log('--- Passwords reset ---');

  // Verify
  const updated = await prisma.user.findMany({ select: { email: true, hashedPassword: true } });
  for (const u of updated) {
    const v1 = await bcrypt.compare('nexquant123', u.hashedPassword || '');
    const v2 = await bcrypt.compare('test1234', u.hashedPassword || '');
    console.log(u.email, '| nexquant123:', v1, '| test1234:', v2);
  }

  await prisma.$disconnect();
}
test().catch(console.error);
