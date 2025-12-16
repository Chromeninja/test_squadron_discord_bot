import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor, act } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';

import SearchableSelect, { type SelectOption } from './SearchableSelect';

const options: SelectOption[] = [
  { id: '1', name: 'Alpha', category: 'Team' },
  { id: '2', name: 'Bravo', category: 'Squad' },
];

const Harness = ({ onChange }: { onChange: (id: string | null) => void }) => {
  const [value, setValue] = useState<string | null>(null);

  return (
    <SearchableSelect
      options={options}
      selected={value}
      onChange={(val) => {
        setValue(val);
        onChange(val);
      }}
    />
  );
};

describe('SearchableSelect', () => {
  it('closes the dropdown when clicking outside', async () => {
    const onChange = vi.fn();
    render(
      <div>
        <Harness onChange={onChange} />
        <button data-testid="outside">outside</button>
      </div>
    );

    const input = screen.getByRole('combobox');
    await act(async () => {
      input.focus();
    });

    // Dropdown opens on focus
    expect(await screen.findByRole('listbox')).toBeInTheDocument();

    // Click outside component
    await act(async () => {
      fireEvent.mouseDown(screen.getByTestId('outside'));
    });

    await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });
  });

  it('clears the selection when pressing the clear button', async () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);

    const input = screen.getByRole('combobox');
    await act(async () => {
      input.focus();
    });

    const option = await screen.findByText('Team / #Alpha');
    await act(async () => {
      fireEvent.click(option);
    });
    expect(onChange).toHaveBeenCalledWith('1');

    const clearButton = await screen.findByRole('button', { name: /clear selection/i });
    await act(async () => {
      fireEvent.click(clearButton);
    });

    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.queryByText('Team / #Alpha')).not.toBeInTheDocument();
  });
});
