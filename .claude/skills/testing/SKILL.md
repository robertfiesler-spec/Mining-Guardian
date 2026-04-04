---
name: testing
description: Testing strategies for React/Next.js applications using Vitest, React Testing Library, and Playwright. Use when writing unit tests, component tests, integration tests, or E2E tests. Also use when deciding what to test or setting up test infrastructure.
---

# Testing Skill

Testing patterns for React/Next.js with Vitest, React Testing Library, and Playwright.

## Test Strategy

### What to Test

| Layer | Tool | What | Coverage Target |
|-------|------|------|-----------------|
| Unit | Vitest | Pure functions, hooks, utilities | 80%+ |
| Component | RTL | UI behavior, user interactions | Key flows |
| Integration | RTL + MSW | Data fetching, form submission | Critical paths |
| E2E | Playwright | Full user journeys | Happy paths |

### What NOT to Test

- Implementation details (internal state, private methods)
- Third-party library internals
- Styles (unless business logic depends on them)
- Constant values

## Vitest Setup

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['node_modules/', 'tests/'],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
});
```

```typescript
// tests/setup.ts
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
});

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));
```

## Unit Tests

### Testing Pure Functions

```typescript
// lib/utils.test.ts
import { describe, it, expect } from 'vitest';
import { formatPrice, calculateDiscount } from './utils';

describe('formatPrice', () => {
  it('formats number as USD currency', () => {
    expect(formatPrice(1234.5)).toBe('$1,234.50');
  });

  it('handles zero', () => {
    expect(formatPrice(0)).toBe('$0.00');
  });

  it('handles negative numbers', () => {
    expect(formatPrice(-50)).toBe('-$50.00');
  });
});

describe('calculateDiscount', () => {
  it('applies percentage discount', () => {
    expect(calculateDiscount(100, { type: 'percent', value: 20 })).toBe(80);
  });

  it('applies fixed discount', () => {
    expect(calculateDiscount(100, { type: 'fixed', value: 25 })).toBe(75);
  });

  it('never goes below zero', () => {
    expect(calculateDiscount(10, { type: 'fixed', value: 50 })).toBe(0);
  });
});
```

### Testing Custom Hooks

```typescript
// hooks/use-counter.test.ts
import { renderHook, act } from '@testing-library/react';
import { useCounter } from './use-counter';

describe('useCounter', () => {
  it('initializes with default value', () => {
    const { result } = renderHook(() => useCounter());
    expect(result.current.count).toBe(0);
  });

  it('initializes with provided value', () => {
    const { result } = renderHook(() => useCounter(10));
    expect(result.current.count).toBe(10);
  });

  it('increments count', () => {
    const { result } = renderHook(() => useCounter());
    act(() => result.current.increment());
    expect(result.current.count).toBe(1);
  });

  it('decrements count', () => {
    const { result } = renderHook(() => useCounter(5));
    act(() => result.current.decrement());
    expect(result.current.count).toBe(4);
  });
});
```

## Component Tests

### Testing User Interactions

```typescript
// components/LoginForm.test.tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
import { LoginForm } from './LoginForm';

describe('LoginForm', () => {
  it('renders email and password inputs', () => {
    render(<LoginForm onSubmit={vi.fn()} />);
    
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it('calls onSubmit with credentials', async () => {
    const user = userEvent.setup();
    const handleSubmit = vi.fn();
    
    render(<LoginForm onSubmit={handleSubmit} />);
    
    await user.type(screen.getByLabelText(/email/i), 'test@example.com');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    
    expect(handleSubmit).toHaveBeenCalledWith({
      email: 'test@example.com',
      password: 'password123',
    });
  });

  it('shows validation errors', async () => {
    const user = userEvent.setup();
    render(<LoginForm onSubmit={vi.fn()} />);
    
    await user.click(screen.getByRole('button', { name: /sign in/i }));
    
    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
    expect(screen.getByText(/password is required/i)).toBeInTheDocument();
  });

  it('disables submit button while loading', () => {
    render(<LoginForm onSubmit={vi.fn()} isLoading />);
    
    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled();
  });
});
```

### Testing Async Behavior

```typescript
// components/UserProfile.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { UserProfile } from './UserProfile';
import { server } from '@/tests/mocks/server';
import { http, HttpResponse } from 'msw';

describe('UserProfile', () => {
  it('shows loading state', () => {
    render(<UserProfile userId="1" />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('displays user data', async () => {
    render(<UserProfile userId="1" />);
    
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });
  });

  it('shows error on fetch failure', async () => {
    server.use(
      http.get('/api/users/:id', () => {
        return HttpResponse.json({ error: 'Not found' }, { status: 404 });
      })
    );

    render(<UserProfile userId="999" />);
    
    await waitFor(() => {
      expect(screen.getByText(/user not found/i)).toBeInTheDocument();
    });
  });
});
```

## E2E Tests with Playwright

```typescript
// e2e/auth.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('user can sign up', async ({ page }) => {
    await page.goto('/signup');
    
    await page.getByLabel('Email').fill('newuser@example.com');
    await page.getByLabel('Password').fill('SecurePass123');
    await page.getByLabel('Confirm Password').fill('SecurePass123');
    await page.getByRole('button', { name: /create account/i }).click();
    
    await expect(page).toHaveURL('/dashboard');
    await expect(page.getByText(/welcome/i)).toBeVisible();
  });

  test('user can log in', async ({ page }) => {
    await page.goto('/login');
    
    await page.getByLabel('Email').fill('existing@example.com');
    await page.getByLabel('Password').fill('password123');
    await page.getByRole('button', { name: /sign in/i }).click();
    
    await expect(page).toHaveURL('/dashboard');
  });

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/login');
    
    await page.getByLabel('Email').fill('wrong@example.com');
    await page.getByLabel('Password').fill('wrongpassword');
    await page.getByRole('button', { name: /sign in/i }).click();
    
    await expect(page.getByText(/invalid credentials/i)).toBeVisible();
    await expect(page).toHaveURL('/login');
  });
});
```

## MSW for API Mocking

```typescript
// tests/mocks/handlers.ts
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/users/:id', ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      name: 'John Doe',
      email: 'john@example.com',
    });
  }),

  http.post('/api/users', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: '123', ...body }, { status: 201 });
  }),
];

// tests/mocks/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

## File References

- `references/testing-patterns.md` - Advanced testing scenarios
- `scripts/test-utils.ts` - Custom render functions and utilities
