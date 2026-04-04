---
name: react-patterns
description: React component architecture, custom hooks, and performance optimization patterns for Next.js App Router. Use when building new components, refactoring existing ones, optimizing performance, or deciding between Server and Client Components.
---

# React Patterns

Patterns for building maintainable, performant React components in Next.js.

## Server vs Client Components

**Default to Server Components.** Add `'use client'` only when you need:

- Event handlers (onClick, onChange, etc.)
- Browser APIs (localStorage, window, etc.)
- Hooks that use state or effects (useState, useEffect, etc.)
- Client-only libraries

```typescript
// Server Component (default) - fetches data, no JS shipped
export default async function UserProfile({ userId }: { userId: string }) {
  const user = await getUser(userId); // Direct DB/API call
  return <ProfileCard user={user} />;
}

// Client Component - only when interactivity needed
'use client';
export function LikeButton({ postId }: { postId: string }) {
  const [liked, setLiked] = useState(false);
  return <button onClick={() => setLiked(!liked)}>♥</button>;
}
```

## Composition Patterns

### Compound Components

For related components that share implicit state:

```typescript
// Usage
<Tabs defaultValue="account">
  <Tabs.List>
    <Tabs.Trigger value="account">Account</Tabs.Trigger>
    <Tabs.Trigger value="settings">Settings</Tabs.Trigger>
  </Tabs.List>
  <Tabs.Content value="account">Account settings...</Tabs.Content>
  <Tabs.Content value="settings">App settings...</Tabs.Content>
</Tabs>
```

### Render Props / Children as Function

When consumers need control over rendering:

```typescript
<DataTable
  data={users}
  columns={columns}
  renderRow={(user) => (
    <tr key={user.id} className={user.isActive ? 'active' : ''}>
      {/* Custom row rendering */}
    </tr>
  )}
/>
```

### Slot Pattern

For flexible layouts:

```typescript
interface CardProps {
  header?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
}

export function Card({ header, footer, children }: CardProps) {
  return (
    <div className="card">
      {header && <div className="card-header">{header}</div>}
      <div className="card-body">{children}</div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  );
}
```

## Custom Hooks

### Data Fetching Hook

```typescript
export function useUser(userId: string) {
  return useQuery({
    queryKey: ['user', userId],
    queryFn: () => fetchUser(userId),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
```

### Form Hook

```typescript
export function useForm<T extends Record<string, unknown>>(initialValues: T) {
  const [values, setValues] = useState(initialValues);
  const [errors, setErrors] = useState<Partial<Record<keyof T, string>>>({});
  
  const setValue = useCallback(<K extends keyof T>(key: K, value: T[K]) => {
    setValues(prev => ({ ...prev, [key]: value }));
    setErrors(prev => ({ ...prev, [key]: undefined }));
  }, []);
  
  const reset = useCallback(() => {
    setValues(initialValues);
    setErrors({});
  }, [initialValues]);
  
  return { values, errors, setValue, setErrors, reset };
}
```

### Toggle Hook

```typescript
export function useToggle(initialValue = false) {
  const [value, setValue] = useState(initialValue);
  
  const toggle = useCallback(() => setValue(v => !v), []);
  const setTrue = useCallback(() => setValue(true), []);
  const setFalse = useCallback(() => setValue(false), []);
  
  return [value, { toggle, setTrue, setFalse }] as const;
}
```

## Performance Patterns

### Memoization

```typescript
// Memoize expensive computations
const sortedItems = useMemo(
  () => items.sort((a, b) => a.price - b.price),
  [items]
);

// Memoize callbacks passed to children
const handleSubmit = useCallback((data: FormData) => {
  submitForm(data);
}, [submitForm]);

// Memoize components that receive object/array props
const MemoizedList = memo(function ItemList({ items }: { items: Item[] }) {
  return items.map(item => <Item key={item.id} {...item} />);
});
```

### Code Splitting

```typescript
// Dynamic imports for heavy components
const HeavyChart = dynamic(() => import('./HeavyChart'), {
  loading: () => <ChartSkeleton />,
  ssr: false, // Client-only if needed
});

// Route-based splitting (automatic in Next.js App Router)
// Each page.tsx is automatically code-split
```

### Virtualization

For long lists, see `references/virtualization.md` for react-window patterns.

## Error Boundaries

```typescript
'use client';

export function ErrorBoundary({ 
  children, 
  fallback 
}: { 
  children: React.ReactNode;
  fallback: React.ReactNode;
}) {
  return (
    <ErrorBoundaryPrimitive fallback={fallback}>
      {children}
    </ErrorBoundaryPrimitive>
  );
}

// Usage in layout
<ErrorBoundary fallback={<ErrorCard />}>
  <DashboardContent />
</ErrorBoundary>
```

## File References

- `references/hooks-patterns.md` - Extended custom hooks library
- `references/virtualization.md` - List virtualization patterns
