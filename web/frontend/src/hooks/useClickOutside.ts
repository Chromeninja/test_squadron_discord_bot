import { useEffect, type RefObject } from 'react';

/**
 * Hook that invokes `handler` when a mousedown event occurs outside every
 * one of the supplied refs.
 *
 * @example
 * const dropdownRef = useRef<HTMLDivElement>(null);
 * useClickOutside([dropdownRef], () => setOpen(false));
 */
export function useClickOutside(
  refs: RefObject<HTMLElement | null>[],
  handler: () => void,
): void {
  useEffect(() => {
    const listener = (event: MouseEvent) => {
      const target = event.target as Node;
      const isInside = refs.some((ref) => ref.current?.contains(target));
      if (!isInside) handler();
    };

    document.addEventListener('mousedown', listener);
    return () => document.removeEventListener('mousedown', listener);
  }, [refs, handler]);
}
