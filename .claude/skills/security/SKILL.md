---
name: security
description: Security patterns for Next.js applications including authentication, authorization, input validation, and OWASP Top 10 mitigations. Use when implementing auth flows, protecting routes, validating user input, or reviewing code for security vulnerabilities.
---

# Security Skill

Security patterns and best practices for Next.js applications.

## Authentication

### Auth.js (NextAuth) Setup

```typescript
// auth.ts
import NextAuth from 'next-auth';
import GitHub from 'next-auth/providers/github';
import Credentials from 'next-auth/providers/credentials';
import { PrismaAdapter } from '@auth/prisma-adapter';
import { prisma } from '@/lib/prisma';

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PrismaAdapter(prisma),
  providers: [
    GitHub,
    Credentials({
      credentials: {
        email: { label: 'Email', type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        // Validate credentials
        const user = await prisma.user.findUnique({
          where: { email: credentials.email as string },
        });
        
        if (!user) return null;
        
        const valid = await bcrypt.compare(
          credentials.password as string,
          user.passwordHash
        );
        
        if (!valid) return null;
        
        return { id: user.id, email: user.email, name: user.name };
      },
    }),
  ],
  callbacks: {
    async session({ session, user }) {
      session.user.id = user.id;
      session.user.role = user.role;
      return session;
    },
  },
});
```

### Route Protection

```typescript
// middleware.ts
import { auth } from '@/auth';

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const isOnDashboard = req.nextUrl.pathname.startsWith('/dashboard');
  const isOnAuth = req.nextUrl.pathname.startsWith('/login');

  if (isOnDashboard && !isLoggedIn) {
    return Response.redirect(new URL('/login', req.nextUrl));
  }

  if (isOnAuth && isLoggedIn) {
    return Response.redirect(new URL('/dashboard', req.nextUrl));
  }
});

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
};
```

### Server Component Protection

```typescript
// app/dashboard/page.tsx
import { auth } from '@/auth';
import { redirect } from 'next/navigation';

export default async function DashboardPage() {
  const session = await auth();
  
  if (!session) {
    redirect('/login');
  }

  // Role-based access
  if (session.user.role !== 'admin') {
    redirect('/unauthorized');
  }

  return <AdminDashboard user={session.user} />;
}
```

### Server Action Protection

```typescript
'use server';

import { auth } from '@/auth';

export async function deletePost(postId: string) {
  const session = await auth();
  
  if (!session) {
    throw new Error('Unauthorized');
  }

  const post = await prisma.post.findUnique({
    where: { id: postId },
  });

  // Authorization: User can only delete their own posts
  if (post?.authorId !== session.user.id) {
    throw new Error('Forbidden');
  }

  await prisma.post.delete({ where: { id: postId } });
  revalidatePath('/posts');
}
```

## Input Validation

### Zod Schemas

```typescript
// lib/validations/user.ts
import { z } from 'zod';

export const CreateUserSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .max(128, 'Password too long')
    .regex(
      /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/,
      'Password must contain uppercase, lowercase, and number'
    ),
  name: z.string().min(1, 'Name required').max(100, 'Name too long'),
});

export const UpdateUserSchema = CreateUserSchema.partial().omit({ password: true });

// Reusable patterns
export const idSchema = z.string().uuid('Invalid ID');
export const paginationSchema = z.object({
  page: z.coerce.number().int().positive().default(1),
  limit: z.coerce.number().int().positive().max(100).default(20),
});
```

### Server Action Validation

```typescript
'use server';

import { CreateUserSchema } from '@/lib/validations/user';

export async function createUser(formData: FormData) {
  const rawData = {
    email: formData.get('email'),
    password: formData.get('password'),
    name: formData.get('name'),
  };

  // Validate - throws ZodError if invalid
  const validated = CreateUserSchema.parse(rawData);

  // Or safe parse for custom error handling
  const result = CreateUserSchema.safeParse(rawData);
  if (!result.success) {
    return {
      errors: result.error.flatten().fieldErrors,
    };
  }

  // Safe to use result.data
}
```

### API Route Validation

```typescript
// app/api/users/route.ts
import { NextResponse } from 'next/server';
import { CreateUserSchema } from '@/lib/validations/user';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const validated = CreateUserSchema.parse(body);
    
    // Create user...
    
    return NextResponse.json({ user }, { status: 201 });
  } catch (error) {
    if (error instanceof z.ZodError) {
      return NextResponse.json(
        { errors: error.flatten().fieldErrors },
        { status: 400 }
      );
    }
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

## OWASP Top 10 Mitigations

### 1. Injection

```typescript
// ✅ Parameterized queries
const user = await prisma.user.findUnique({
  where: { email: userEmail },
});

// ❌ NEVER string concatenation
const user = await prisma.$queryRawUnsafe(
  `SELECT * FROM users WHERE email = '${userEmail}'`
);
```

### 2. Broken Authentication

- Use proven auth library (Auth.js)
- Implement rate limiting on login
- Use secure session management
- Require strong passwords

### 3. Sensitive Data Exposure

```typescript
// Strip sensitive fields before returning
const { passwordHash, ...safeUser } = user;
return safeUser;

// Or use Prisma select
const user = await prisma.user.findUnique({
  where: { id },
  select: { id: true, email: true, name: true }, // Explicit allowlist
});
```

### 4. XXE - Not typically applicable to JSON APIs

### 5. Broken Access Control

```typescript
// Always verify ownership
async function updatePost(postId: string, userId: string, data: UpdateData) {
  const post = await prisma.post.findUnique({ where: { id: postId } });
  
  if (!post) throw new NotFoundError();
  if (post.authorId !== userId) throw new ForbiddenError();
  
  return prisma.post.update({ where: { id: postId }, data });
}
```

### 6. Security Misconfiguration

See security headers in `references/security-headers.md`.

### 7. XSS

React escapes by default. Watch for:
- `dangerouslySetInnerHTML`
- Rendering URLs from user input
- `href="javascript:..."` attacks

### 8. Insecure Deserialization

Always validate before parsing:

```typescript
// Validate JSON structure
const data = JSON.parse(body);
const validated = MySchema.parse(data);
```

### 9. Using Components with Known Vulnerabilities

```bash
# Regular audits
npm audit
npm audit fix

# CI/CD integration
npm audit --audit-level=high
```

### 10. Insufficient Logging & Monitoring

```typescript
// Log security events
logger.warn('Failed login attempt', {
  email: maskEmail(email),
  ip: getClientIp(request),
  userAgent: request.headers.get('user-agent'),
});
```

## File References

- `references/security-headers.md` - Complete security headers config
- `references/auth-patterns.md` - Advanced auth patterns (MFA, SSO)
