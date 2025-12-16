import { ReactNode, useState } from 'react';

interface AccordionSectionProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  level?: 1 | 2;
}

const AccordionSection = ({ title, children, defaultOpen = false, level = 1 }: AccordionSectionProps) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  const levelStyles = {
    1: {
      container: 'rounded-xl border border-slate-600 bg-slate-800/60',
      header: 'px-6 py-4 bg-slate-800/80',
      title: 'text-lg font-semibold text-white',
      content: 'px-6 pb-6 pt-2',
    },
    2: {
      container: 'rounded-lg border border-slate-700 bg-slate-800/40',
      header: 'px-5 py-3 bg-slate-800/60',
      title: 'text-base font-semibold text-white',
      content: 'px-5 pb-5 pt-2',
    },
  };

  const styles = levelStyles[level];

  return (
    <div className={styles.container}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`${styles.header} flex w-full items-center justify-between transition hover:bg-slate-700/60`}
      >
        <span className={styles.title}>{title}</span>
        <svg
          className={`h-5 w-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {isOpen && <div className={styles.content}>{children}</div>}
    </div>
  );
};

export default AccordionSection;
