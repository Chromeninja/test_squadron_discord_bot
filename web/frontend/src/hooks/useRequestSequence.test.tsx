import '@testing-library/jest-dom';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useRequestSequence } from './useRequestSequence';

describe('useRequestSequence', () => {
  it('tracks the latest request id and invalidates older ones', () => {
    const { result } = renderHook(() => useRequestSequence());

    let firstRequestId = 0;
    let secondRequestId = 0;

    act(() => {
      firstRequestId = result.current.next();
      secondRequestId = result.current.next();
    });

    expect(result.current.isCurrent(firstRequestId)).toBe(false);
    expect(result.current.isCurrent(secondRequestId)).toBe(true);

    act(() => {
      result.current.invalidate();
    });

    expect(result.current.isCurrent(secondRequestId)).toBe(false);
  });
});