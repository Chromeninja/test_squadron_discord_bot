import { useMemo, useRef } from 'react';

import { cn } from '../utils/cn';

interface DiscordMarkdownEditorProps {
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  helperText?: string;
  disabled?: boolean;
  className?: string;
}

type MarkdownAction =
  | 'bold'
  | 'italic'
  | 'underline'
  | 'strike'
  | 'bullet'
  | 'numbered'
  | 'quote'
  | 'inlineCode'
  | 'codeBlock'
  | 'spoiler'
  | 'link';

interface ToolbarItem {
  action: MarkdownAction;
  label: string;
  title: string;
}

const TOOLBAR_ITEMS: ToolbarItem[] = [
  { action: 'bold', label: 'B', title: 'Bold' },
  { action: 'italic', label: 'I', title: 'Italic' },
  { action: 'underline', label: 'U', title: 'Underline' },
  { action: 'strike', label: 'S', title: 'Strikethrough' },
  { action: 'bullet', label: '• List', title: 'Bulleted list' },
  { action: 'numbered', label: '1. List', title: 'Numbered list' },
  { action: 'quote', label: 'Quote', title: 'Block quote' },
  { action: 'inlineCode', label: '</>', title: 'Inline code' },
  { action: 'codeBlock', label: '{ }', title: 'Code block' },
  { action: 'spoiler', label: 'Spoiler', title: 'Spoiler' },
  { action: 'link', label: 'Link', title: 'Markdown link' },
];

export default function DiscordMarkdownEditor({
  label,
  value,
  onChange,
  placeholder,
  rows = 3,
  helperText,
  disabled = false,
  className,
}: DiscordMarkdownEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const markdownHelp = useMemo(
    () =>
      helperText ??
      'Supports Discord markdown: **bold**, *italic*, __underline__, ~~strike~~, lists, > quotes, `code`, and ```code blocks```.',
    [helperText]
  );

  const applyWithSelection = (
    nextText: string,
    selectionStart: number,
    selectionEnd: number
  ) => {
    onChange(nextText);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(selectionStart, selectionEnd);
    });
  };

  const wrapSelection = (prefix: string, suffix: string, fallbackText: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = value.slice(start, end);
    const insert = selected || fallbackText;

    const nextValue = `${value.slice(0, start)}${prefix}${insert}${suffix}${value.slice(end)}`;
    const selectFrom = start + prefix.length;
    const selectTo = selectFrom + insert.length;

    applyWithSelection(nextValue, selectFrom, selectTo);
  };

  const prefixLines = (prefixFactory: (index: number) => string, fallbackText: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = value.slice(start, end) || fallbackText;
    const lines = selected.split('\n');
    const transformed = lines
      .map((line, index) => `${prefixFactory(index)}${line}`)
      .join('\n');

    const nextValue = `${value.slice(0, start)}${transformed}${value.slice(end)}`;
    applyWithSelection(nextValue, start, start + transformed.length);
  };

  const applyMarkdown = (action: MarkdownAction) => {
    switch (action) {
      case 'bold':
        wrapSelection('**', '**', 'bold text');
        break;
      case 'italic':
        wrapSelection('*', '*', 'italic text');
        break;
      case 'underline':
        wrapSelection('__', '__', 'underlined text');
        break;
      case 'strike':
        wrapSelection('~~', '~~', 'struck text');
        break;
      case 'inlineCode':
        wrapSelection('`', '`', 'code');
        break;
      case 'spoiler':
        wrapSelection('||', '||', 'spoiler');
        break;
      case 'link':
        wrapSelection('[', '](https://example.com)', 'link text');
        break;
      case 'codeBlock':
        wrapSelection('```\n', '\n```', 'code block');
        break;
      case 'bullet':
        prefixLines(() => '- ', 'list item');
        break;
      case 'numbered':
        prefixLines((index) => `${index + 1}. `, 'list item');
        break;
      case 'quote':
        prefixLines(() => '> ', 'quoted text');
        break;
      default:
        break;
    }
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;

    const key = event.key.toLowerCase();
    if (key === 'b') {
      event.preventDefault();
      applyMarkdown('bold');
      return;
    }

    if (key === 'i') {
      event.preventDefault();
      applyMarkdown('italic');
      return;
    }

    if (key === 'u') {
      event.preventDefault();
      applyMarkdown('underline');
    }
  };

  const inputId = label ? label.toLowerCase().replace(/\s+/g, '-') : undefined;

  return (
    <div className={cn('space-y-2', className)}>
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-gray-300">
          {label}
        </label>
      )}

      <div className="flex flex-wrap gap-2 rounded border border-slate-700 bg-slate-900/50 p-2">
        {TOOLBAR_ITEMS.map((item) => (
          <button
            key={item.action}
            type="button"
            onClick={() => applyMarkdown(item.action)}
            disabled={disabled}
            title={item.title}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-gray-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {item.label}
          </button>
        ))}
      </div>

      <textarea
        ref={textareaRef}
        id={inputId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        rows={rows}
        disabled={disabled}
        className="w-full min-h-[80px] resize-y rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
      />

      <div className="flex items-center justify-between text-xs text-gray-500">
        <p>{markdownHelp}</p>
        <span>{value.length} chars</span>
      </div>
      <p className="text-xs text-gray-500">
        Discord best practice: keep ticket prompts concise and avoid mass mentions like @everyone.
      </p>
    </div>
  );
}
