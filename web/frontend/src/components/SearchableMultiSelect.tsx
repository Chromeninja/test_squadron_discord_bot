import { useMemo, useState, type KeyboardEvent } from 'react';

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
  };

  const removeSelection = (optionId: string) => {
    onChange(selected.filter((id) => id !== optionId));
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !query && selected.length > 0) {
      event.preventDefault();
      const last = selected[selected.length - 1];
      removeSelection(last);
    }
  };

  return (
    <div className="space-y-2">
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
          placeholder={placeholder}
          className="flex-1 bg-transparent text-sm focus:outline-none"
        />
      </div>

      <div className="max-h-60 overflow-y-auto rounded-md border border-slate-700 bg-slate-900">
        {filteredOptions.length === 0 ? (
          <div className="p-3 text-sm text-gray-400">No roles match your search.</div>
        ) : (
          <ul>
            {filteredOptions.map((option) => (
              <li
                key={`${componentId}-${option.id}`}
                className={`cursor-pointer px-3 py-2 text-sm transition hover:bg-slate-800 ${
                  selectedSet.has(option.id) ? 'bg-slate-800 text-indigo-300' : 'text-gray-200'
                }`}
                onClick={() => toggleSelection(option.id)}
              >
                {option.name}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};

export default SearchableMultiSelect;
