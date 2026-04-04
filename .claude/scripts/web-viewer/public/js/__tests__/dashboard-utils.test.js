import { describe, it, expect } from 'vitest';

const {
  groupStoriesByType,
  getSessionStatusBadge,
  escapeHtml,
} = await import('../dashboard.js');

// -- groupStoriesByType --

describe('groupStoriesByType', () => {
  it('groups stories correctly by their type field', () => {
    const stories = [
      { id: 'S1', type: 'Setup', priority: 1 },
      { id: 'S2', type: 'Core', priority: 2 },
      { id: 'S3', type: 'Setup', priority: 3 },
    ];

    const grouped = groupStoriesByType(stories);

    expect(Object.keys(grouped)).toEqual(expect.arrayContaining(['Setup', 'Core']));
    expect(grouped['Setup']).toHaveLength(2);
    expect(grouped['Core']).toHaveLength(1);
  });

  it('sorts stories by priority within each group', () => {
    const stories = [
      { id: 'S3', type: 'API', priority: 3 },
      { id: 'S1', type: 'API', priority: 1 },
      { id: 'S2', type: 'API', priority: 2 },
    ];

    const grouped = groupStoriesByType(stories);

    expect(grouped['API'][0].id).toBe('S1');
    expect(grouped['API'][1].id).toBe('S2');
    expect(grouped['API'][2].id).toBe('S3');
  });

  it('returns an empty object for an empty array', () => {
    const grouped = groupStoriesByType([]);
    expect(grouped).toEqual({});
  });

  it('groups stories without a type under "Other"', () => {
    const stories = [
      { id: 'S1', priority: 1 },
      { id: 'S2', type: 'Core', priority: 2 },
    ];

    const grouped = groupStoriesByType(stories);

    expect(grouped['Other']).toHaveLength(1);
    expect(grouped['Other'][0].id).toBe('S1');
    expect(grouped['Core']).toHaveLength(1);
  });
});

// -- getSessionStatusBadge --

describe('getSessionStatusBadge', () => {
  it('returns a success badge for "running"', () => {
    const badge = getSessionStatusBadge('running');
    expect(badge).toContain('badge-success');
    expect(badge).toContain('Running');
  });

  it('returns an info badge for "completed"', () => {
    const badge = getSessionStatusBadge('completed');
    expect(badge).toContain('badge-info');
    expect(badge).toContain('Completed');
  });

  it('returns an error badge for "failed"', () => {
    const badge = getSessionStatusBadge('failed');
    expect(badge).toContain('badge-error');
    expect(badge).toContain('Failed');
  });

  it('returns an empty string for unknown status', () => {
    expect(getSessionStatusBadge('unknown-status')).toBe('');
    expect(getSessionStatusBadge(undefined)).toBe('');
  });
});

// -- escapeHtml --

describe('escapeHtml', () => {
  it('escapes < and > characters', () => {
    expect(escapeHtml('<script>')).toBe('&lt;script&gt;');
  });

  it('escapes & character', () => {
    expect(escapeHtml('a&b')).toBe('a&amp;b');
  });

  it('escapes double quotes', () => {
    expect(escapeHtml('say "hello"')).toBe('say &quot;hello&quot;');
  });

  it('escapes single quotes', () => {
    expect(escapeHtml("it's")).toBe("it&#039;s");
  });

  it('returns normal text unchanged', () => {
    expect(escapeHtml('Hello World')).toBe('Hello World');
  });

  it('returns empty string for falsy input', () => {
    expect(escapeHtml('')).toBe('');
    expect(escapeHtml(null)).toBe('');
    expect(escapeHtml(undefined)).toBe('');
  });
});
