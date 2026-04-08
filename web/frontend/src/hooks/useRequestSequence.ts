import { useCallback, useMemo, useRef } from 'react';

interface RequestSequenceController {
  next: () => number;
  isCurrent: (requestId: number) => boolean;
  invalidate: () => void;
}

export function useRequestSequence(): RequestSequenceController {
  const requestSequenceRef = useRef(0);

  const next = useCallback(() => {
    requestSequenceRef.current += 1;
    return requestSequenceRef.current;
  }, []);

  const isCurrent = useCallback((requestId: number) => {
    return requestId === requestSequenceRef.current;
  }, []);

  const invalidate = useCallback(() => {
    requestSequenceRef.current += 1;
  }, []);

  return useMemo(
    () => ({
      next,
      isCurrent,
      invalidate,
    }),
    [invalidate, isCurrent, next],
  );
}