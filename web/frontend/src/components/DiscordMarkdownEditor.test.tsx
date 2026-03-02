import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useState } from 'react';

import DiscordMarkdownEditor from './DiscordMarkdownEditor';

function Harness() {
  const [value, setValue] = useState('');

  return (
    <DiscordMarkdownEditor
      label="Test Editor"
      value={value}
      onChange={setValue}
      placeholder="Type here"
    />
  );
}

describe('DiscordMarkdownEditor', () => {
  it('wraps selected text with bold markdown', () => {
    render(<Harness />);

    const textarea = screen.getByRole('textbox', { name: /test editor/i }) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'hello world' } });

    textarea.focus();
    textarea.setSelectionRange(0, 5);

    fireEvent.click(screen.getByRole('button', { name: 'B' }));

    expect(textarea.value).toBe('**hello** world');
  });

  it('formats multiline selection into bullets', () => {
    render(<Harness />);

    const textarea = screen.getByRole('textbox', { name: /test editor/i }) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'first\nsecond' } });

    textarea.focus();
    textarea.setSelectionRange(0, textarea.value.length);

    fireEvent.click(screen.getByRole('button', { name: '• List' }));

    expect(textarea.value).toBe('- first\n- second');
  });
});
