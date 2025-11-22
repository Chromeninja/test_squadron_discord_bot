import { useMemo, useState, type KeyboardEvent } from 'react';

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
    }
  };

  const getDisplayLabel = (option: SelectOption) => {
    if (formatLabel) {
      return formatLabel(option);
    }
    return option.category ? `${option.category} / #${option.name}` : `#${option.name}`;
  };

  return (
    <div className="relative space-y-2">
      <div className="flex items-center gap-2 rounded-md border border-slate-600 bg-slate-800 p-2 focus-within:border-indigo-400">
        {selectedOption && !isOpen && (
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-600/20 px-3 py-1 text-sm text-indigo-200">
            {getDisplayLabel(selectedOption)}
            <button
              type="button"
              className="text-xs text-indigo-300 hover:text-white"
              onClick={handleClear}
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
          className="flex-1 bg-transparent text-sm focus:outline-none"
        />
      </div>

      {isOpen && (
        <div className="absolute z-10 w-full max-h-60 overflow-y-auto rounded-md border border-slate-700 bg-slate-900 shadow-lg">
          {filteredOptions.length === 0 ? (
            <div className="p-3 text-sm text-gray-400">No matches found.</div>
          ) : (
            <ul>
              {filteredOptions.map((option) => (
                <li
                  key={option.id}
                  className={`cursor-pointer px-3 py-2 text-sm transition hover:bg-slate-800 ${
                    option.id === selected ? 'bg-slate-800 text-indigo-300' : 'text-gray-200'
                  }`}
                  onClick={() => handleSelect(option.id)}
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
