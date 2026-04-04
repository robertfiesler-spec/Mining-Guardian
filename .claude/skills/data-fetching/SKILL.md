---
name: data-fetching
description: Data fetching patterns for Next.js App Router including Server Actions, React Query, caching strategies, and streaming. Use when implementing API calls, form submissions, real-time updates, or optimizing data loading performance.
---

# Data Fetching Skill

Patterns for fetching, mutating, and caching data in Next.js App Router.

## Decision Tree

```
Need to fetch data?
├── Server Component? → Direct fetch/DB call (default)
├── Client-side with caching? → React Query / SWR
├── Real-time updates? → WebSocket / SSE + React Query
└── Form submission? → Server Action

Need to mutate data?
├── Form? → Server Action with useActionState
├── Programmatic? → Server Action called from client
└── Optimistic UI? → useOptimistic + Server Action
```

## Server Components (Default)

Fetch directly in async Server Components:

```typescript
// app/users/page.tsx - Server Component
export default async function UsersPage() {
  // Direct DB/API call - no client JS
  const users = await prisma.user.findMany({
    take: 10,
    orderBy: { createdAt: 'desc' },
  });

  return <UserList users={users} />;
}

// With fetch and caching
async function getProducts() {
  const res = await fetch('https://api.example.com/products', {
    next: { revalidate: 3600 }, // Cache for 1 hour
  });
  return res.json();
}
```

## Server Actions

For mutations and form submissions:

```typescript
// app/actions/users.ts
'use server';

import { revalidatePath } from 'next/cache';
import { redirect } from 'next/navigation';
import { z } from 'zod';

const CreateUserSchema = z.object({
  email: z.string().email(),
  name: z.string().min(1),
});

export async function createUser(prevState: any, formData: FormData) {
  // 1. Validate
  const validated = CreateUserSchema.safeParse({
    email: formData.get('email'),
    name: formData.get('name'),
  });

  if (!validated.success) {
    return { errors: validated.error.flatten().fieldErrors };
  }

  // 2. Mutate
  try {
    await prisma.user.create({ data: validated.data });
  } catch (error) {
    return { errors: { _form: ['Failed to create user'] } };
  }

  // 3. Revalidate and redirect
  revalidatePath('/users');
  redirect('/users');
}
```

### Using Server Actions in Forms

```typescript
'use client';

import { useActionState } from 'react';
import { createUser } from '@/app/actions/users';

export function CreateUserForm() {
  const [state, formAction, isPending] = useActionState(createUser, null);

  return (
    <form action={formAction}>
      <input name="email" type="email" required />
      {state?.errors?.email && (
        <p className="text-red-500">{state.errors.email}</p>
      )}
      
      <input name="name" required />
      {state?.errors?.name && (
        <p className="text-red-500">{state.errors.name}</p>
      )}
      
      <button type="submit" disabled={isPending}>
        {isPending ? 'Creating…' : 'Create User'}
      </button>
    </form>
  );
}
```

## React Query (Client-Side)

For client components needing caching, refetching, or real-time updates:

### Setup

```typescript
// providers/query-provider.tsx
'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () => new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 60 * 1000, // 1 minute
          refetchOnWindowFocus: false,
        },
      },
    })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
}
```

### Query Hooks

```typescript
// hooks/use-users.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      const res = await fetch('/api/users');
      if (!res.ok) throw new Error('Failed to fetch');
      return res.json();
    },
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateUserInput) => {
      const res = await fetch('/api/users', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('Failed to create');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}
```

## Optimistic Updates

```typescript
'use client';

import { useOptimistic } from 'react';
import { likePost } from '@/app/actions/posts';

export function LikeButton({ postId, initialLikes }: Props) {
  const [optimisticLikes, addOptimisticLike] = useOptimistic(
    initialLikes,
    (state, newLike: Like) => [...state, newLike]
  );

  async function handleLike() {
    const tempLike = { id: `temp-${Date.now()}`, userId: currentUser.id };
    addOptimisticLike(tempLike);
    await likePost(postId);
  }

  return (
    <button onClick={handleLike}>
      ♥ {optimisticLikes.length}
    </button>
  );
}
```

## Streaming with Suspense

```typescript
// app/dashboard/page.tsx
import { Suspense } from 'react';

export default function DashboardPage() {
  return (
    <div>
      <h1>Dashboard</h1>
      
      {/* Fast data loads immediately */}
      <UserGreeting />
      
      {/* Slow data streams in */}
      <Suspense fallback={<AnalyticsSkeleton />}>
        <Analytics />
      </Suspense>
      
      <Suspense fallback={<RecentActivitySkeleton />}>
        <RecentActivity />
      </Suspense>
    </div>
  );
}

// Async Server Component - automatically streams
async function Analytics() {
  const data = await getAnalytics(); // Slow query
  return <AnalyticsChart data={data} />;
}
```

## Caching Strategies

### Next.js fetch caching

```typescript
// Cache forever (static)
fetch(url, { cache: 'force-cache' });

// Revalidate every hour
fetch(url, { next: { revalidate: 3600 } });

// No cache (dynamic)
fetch(url, { cache: 'no-store' });

// Tag-based revalidation
fetch(url, { next: { tags: ['products'] } });

// Then revalidate by tag
import { revalidateTag } from 'next/cache';
revalidateTag('products');
```

### Route segment config

```typescript
// Force dynamic rendering
export const dynamic = 'force-dynamic';

// Force static
export const dynamic = 'force-static';

// Revalidate interval
export const revalidate = 3600;
```

## Error Handling

```typescript
// app/users/error.tsx
'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div>
      <h2>Something went wrong!</h2>
      <p>{error.message}</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}

// app/users/loading.tsx
export default function Loading() {
  return <UserListSkeleton />;
}
```

## File References

- `references/caching-deep-dive.md` - Advanced caching patterns
- `references/react-query-patterns.md` - Complex React Query scenarios
