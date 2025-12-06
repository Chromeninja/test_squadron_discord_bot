import { useMemo, useRef, useState, type KeyboardEvent, type FocusEvent } from 'react';

export interface MultiSelectOption {
  id: string;  // Changed from number to string to preserve 64-bit Discord snowflake precision
  name: string;
}

interface SearchableMultiSelectProps {
  options: MultiSelectOption[];
  selected: string[];  // Changed from number[] to string[]
  onChange: (ids: string[]) => void;  // Changed from number[] to string[]
  placeholder?: string;
  componentId?: string;  // Optional unique ID to prevent key collisions
}

const SearchableMultiSelect = ({
  options,
  selected,
  onChange,
  placeholder = 'Type to search roles...',
  componentId = 'default',
}: SearchableMultiSelectProps) => {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const filteredOptions = useMemo(() => {
    if (!query.trim()) {
      return options;
    }
    const lowerQuery = query.toLowerCase();
    return options.filter((option) => option.name.toLowerCase().includes(lowerQuery));
  }, [options, query]);

  const toggleSelection = (optionId: string) => {
    if (selectedSet.has(optionId)) {
      onChange(selected.filter((id) => id !== optionId));
    } else {
      onChange([...selected, optionId]);
    }
    setIsOpen(true);
  };

  const removeSelection = (optionId: string) => {
    onChange(selected.filter((id) => id !== optionId));
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !query && selected.length > 0) {
      event.preventDefault();
      const last = selected[selected.length - 1];
      removeSelection(last);
      return;
    }

    if (event.key === 'Escape') {
      setIsOpen(false);
      setHighlightedIndex(-1);
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setIsOpen(true);
      setHighlightedIndex((prev) => {
        const next = prev + 1;
        return next >= filteredOptions.length ? 0 : next;
      });
      return;
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setIsOpen(true);
      setHighlightedIndex((prev) => {
        if (prev <= 0) {
          return filteredOptions.length - 1;
        }
        return prev - 1;
      });
      return;
    }

    if (event.key === 'Enter' && highlightedIndex >= 0 && highlightedIndex < filteredOptions.length) {
      event.preventDefault();
      const option = filteredOptions[highlightedIndex];
      toggleSelection(option.id);
    }
  };

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget as Node | null;
    if (containerRef.current && next && containerRef.current.contains(next)) {
      return;
    }
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  return (
    <div className="relative space-y-2" ref={containerRef} onBlur={handleBlur}>
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-slate-600 bg-slate-800 p-2 focus-within:border-indigo-400">
        {selected.map((id) => {
          const selectedOption = options.find((opt) => opt.id === id);
          const label = selectedOption ? selectedOption.name : `ID ${id}`;
          return (
            <span
              key={`${componentId}-selected-${id}`}
              className="inline-flex items-center gap-1 rounded-full bg-indigo-600/20 px-3 py-1 text-sm text-indigo-200"
            >
              {label}
              <button
                type="button"
                className="text-xs text-indigo-300 hover:text-white"
                onClick={() => removeSelection(id)}
              >
                ×
              </button>
            </span>
          );
        })}
        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleInputKeyDown}
          onFocus={() => setIsOpen(true)}
          placeholder={placeholder}
          className="flex-1 bg-transparent text-sm focus:outline-none"
        />
      </div>

      {isOpen && (
        <div className="absolute z-10 mt-1 w-full max-h-60 overflow-y-auto rounded-md border border-slate-700 bg-slate-900 shadow-lg">
          {filteredOptions.length === 0 ? (
            <div className="p-3 text-sm text-gray-400">No roles match your search.</div>
          ) : (
            <ul>
              {filteredOptions.map((option, index) => (
                <li
                  key={`${componentId}-${option.id}`}
                  className={`cursor-pointer px-3 py-2 text-sm transition hover:bg-slate-800 ${
                    highlightedIndex === index ? 'bg-slate-800 text-indigo-300' : ''
                  } ${selectedSet.has(option.id) ? 'text-indigo-300' : 'text-gray-200'}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => toggleSelection(option.id)}
                  onMouseEnter={() => setHighlightedIndex(index)}
                >
                  {option.name}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default SearchableMultiSelect;
