import { useEffect, useMemo, useRef, useState, type FocusEvent, type KeyboardEvent } from 'react';

export interface SelectOption {
  id: string;  // Changed from number to string to preserve Discord ID precision
  name: string;
  category?: string;
}

interface SearchableSelectProps {
  options: SelectOption[];
  selected: string | null;  // Changed from number to string
  onChange: (id: string | null) => void;  // Changed from number to string
  placeholder?: string;
  formatLabel?: (option: SelectOption) => string;
}

const SearchableSelect = ({
  options,
  selected,
  onChange,
  placeholder = 'Type to search...',
  formatLabel,
}: SearchableSelectProps) => {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const listboxId = useMemo(
    () => `searchable-select-list-${Math.random().toString(36).slice(2, 8)}`,
    []
  );

  const selectedOption = useMemo(
    () => options.find((opt) => opt.id === selected),
    [options, selected]
  );

  const filteredOptions = useMemo(() => {
    if (!query.trim()) {
      return options;
    }
    const lowerQuery = query.toLowerCase();
    return options.filter(
      (option) =>
        option.name.toLowerCase().includes(lowerQuery) ||
        (option.category && option.category.toLowerCase().includes(lowerQuery))
    );
  }, [options, query]);

  const handleSelect = (optionId: string) => {
    onChange(optionId);
    setQuery('');
    setIsOpen(false);
  };

  const handleClear = () => {
    onChange(null);
    setQuery('');
    setIsOpen(false);
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setIsOpen(false);
      setQuery('');
    } else if (event.key === 'Backspace' && !query && selected !== null) {
      event.preventDefault();
      handleClear();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      setIsOpen(true);
      setHighlightedIndex((prev) => {
        const next = prev + 1;
        if (next >= filteredOptions.length) {
          return filteredOptions.length ? 0 : -1;
        }
        return next;
      });
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setIsOpen(true);
      setHighlightedIndex((prev) => {
        if (prev <= 0) {
          return filteredOptions.length ? filteredOptions.length - 1 : -1;
        }
        return prev - 1;
      });
    } else if (event.key === 'Enter' && highlightedIndex >= 0 && highlightedIndex < filteredOptions.length) {
      event.preventDefault();
      const option = filteredOptions[highlightedIndex];
      handleSelect(option.id);
      setHighlightedIndex(-1);
    }
  };

  useEffect(() => {
    const handleDocumentClick = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && containerRef.current && !containerRef.current.contains(target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleDocumentClick);
    return () => {
      document.removeEventListener('mousedown', handleDocumentClick);
    };
  }, []);

  const getDisplayLabel = (option: SelectOption) => {
    if (formatLabel) {
      return formatLabel(option);
    }
    return option.category ? `${option.category} / #${option.name}` : `#${option.name}`;
  };

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget as Node | null;
    if (containerRef.current && next && containerRef.current.contains(next)) {
      return;
    }
    setIsOpen(false);
    setHighlightedIndex(-1);
  };

  useEffect(() => {
    if (!isOpen) {
      setHighlightedIndex(-1);
      return;
    }

    const selectedIndex = filteredOptions.findIndex((opt) => opt.id === selected);
    if (selectedIndex >= 0) {
      setHighlightedIndex(selectedIndex);
    } else if (filteredOptions.length > 0) {
      setHighlightedIndex(0);
    } else {
      setHighlightedIndex(-1);
    }
  }, [filteredOptions, isOpen, selected]);

  return (
    <div className="relative space-y-2" ref={containerRef} onBlur={handleBlur}>
      <div className="flex items-center gap-2 rounded-md border border-slate-600 bg-slate-800 p-2 focus-within:border-indigo-400">
        {selectedOption && !isOpen && (
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600/20 px-3 py-1 text-sm text-indigo-200">
            {getDisplayLabel(selectedOption)}
            <button
              type="button"
              className="text-xs text-indigo-300 hover:text-white"
              onClick={handleClear}
              aria-label="Clear selection"
            >
              ×
            </button>
          </span>
        )}
        <input
          type="text"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleInputKeyDown}
          placeholder={selectedOption && !isOpen ? '' : placeholder}
          role="combobox"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          aria-autocomplete="list"
          className="flex-1 bg-transparent text-sm focus:outline-none"
        />
      </div>

      {isOpen && (
        <div
          className="absolute z-10 w-full max-h-60 overflow-y-auto rounded-md border border-slate-700 bg-slate-900 shadow-lg"
          role="listbox"
          id={listboxId}
        >
          {filteredOptions.length === 0 ? (
            <div className="p-3 text-sm text-gray-400">No matches found.</div>
          ) : (
            <ul>
              {filteredOptions.map((option, index) => (
                <li
                  key={option.id}
                  className={`cursor-pointer px-3 py-2 text-sm transition hover:bg-slate-800 ${
                    highlightedIndex === index || option.id === selected
                      ? 'bg-slate-800 text-indigo-300'
                      : 'text-gray-200'
                  }`}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => handleSelect(option.id)}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  role="option"
                  aria-selected={option.id === selected}
                >
                  {getDisplayLabel(option)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default SearchableSelect;
