import React, { useEffect, useCallback, useRef } from 'react';
import { cn } from '../../utils/cn';
import { modalVariants, type ModalSize, type ModalHeaderVariant } from '../../utils/theme';

export interface ModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal should close */
  onClose: () => void;
  /** Modal title (string or JSX) */
  title?: React.ReactNode;
  /** Modal size */
  size?: ModalSize;
  /** Header color variant */
  headerVariant?: ModalHeaderVariant;
  /** Whether clicking overlay closes modal */
  closeOnOverlayClick?: boolean;
  /** Whether pressing Escape closes modal */
  closeOnEscape?: boolean;
  /** Max height with scroll */
  scrollable?: boolean;
  /** Modal content */
  children: React.ReactNode;
  /** Footer content (typically buttons) */
  footer?: React.ReactNode;
}

/**
 * Modal dialog component with overlay.
 *
 * @example
 * <Modal
 *   open={showModal}
 *   onClose={() => setShowModal(false)}
 *   title="Confirm Delete"
 *   headerVariant="error"
 *   footer={
 *     <>
 *       <Button variant="secondary" onClick={onClose}>Cancel</Button>
 *       <Button variant="danger" onClick={onConfirm}>Delete</Button>
 *     </>
 *   }
 * >
 *   <p>Are you sure you want to delete this item?</p>
 * </Modal>
 */
export function Modal({
  open,
  onClose,
  title,
  size = 'lg',
  headerVariant = 'default',
  closeOnOverlayClick = true,
  closeOnEscape = true,
  scrollable = true,
  children,
  footer,
}: ModalProps) {
  const mouseDownOnOverlayRef = useRef(false);

  // Handle Escape key
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (closeOnEscape && event.key === 'Escape') {
        onClose();
      }
    },
    [closeOnEscape, onClose]
  );

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      // Prevent body scroll when modal is open
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [open, handleKeyDown]);

  const handleOverlayMouseDown = useCallback(() => {
    mouseDownOnOverlayRef.current = true;
  }, []);

  const handleContentMouseDown = useCallback((e: React.MouseEvent) => {
    mouseDownOnOverlayRef.current = false;
    e.stopPropagation(); // Prevent bubbling to overlay
  }, []);

  // Handle overlay click - only close if both mousedown and mouseup were on overlay
  const handleOverlayClick = useCallback(() => {
    if (closeOnOverlayClick && mouseDownOnOverlayRef.current) {
      onClose();
    }
    // Reset for next interaction
    mouseDownOnOverlayRef.current = false;
  }, [closeOnOverlayClick, onClose]);

  if (!open) return null;

  return (
    <div
      className={modalVariants.overlay}
      onMouseDown={handleOverlayMouseDown}
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? 'modal-title' : undefined}
    >
      <div
        className={cn(
          modalVariants.container,
          modalVariants.size[size],
          scrollable && 'max-h-[90vh] flex flex-col'
        )}
        onMouseDown={handleContentMouseDown}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        {title && (
          <ModalHeader variant={headerVariant}>
            <h3 id="modal-title" className="text-xl font-bold">
              {title}
            </h3>
          </ModalHeader>
        )}

        {/* Body */}
        <ModalBody scrollable={scrollable}>{children}</ModalBody>

        {/* Footer */}
        {footer && <ModalFooter>{footer}</ModalFooter>}
      </div>
    </div>
  );
}

// ============================================================================
// Modal sub-components for custom layouts
// ============================================================================

export interface ModalHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Header color variant */
  variant?: ModalHeaderVariant;
}

export function ModalHeader({
  className,
  variant = 'default',
  children,
  ...props
}: ModalHeaderProps) {
  return (
    <div
      className={cn(
        modalVariants.header.base,
        modalVariants.header[variant],
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export interface ModalBodyProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Enable scrolling for long content */
  scrollable?: boolean;
}

export function ModalBody({ className, scrollable = false, children, ...props }: ModalBodyProps) {
  return (
    <div
      className={cn('px-6 py-4', scrollable && 'flex-1 overflow-y-auto', className)}
      {...props}
    >
      {children}
    </div>
  );
}

export interface ModalFooterProps extends React.HTMLAttributes<HTMLDivElement> {}

export function ModalFooter({ className, children, ...props }: ModalFooterProps) {
  return (
    <div
      className={cn('flex justify-end gap-3 border-t border-[#ffbb00]/15 px-6 py-4', className)}
      {...props}
    >
      {children}
    </div>
  );
}

// ============================================================================
// Confirmation Modal (pre-configured for confirm/cancel patterns)
// ============================================================================

export interface ConfirmationModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal should close */
  onClose: () => void;
  /** Callback when confirmed */
  onConfirm: () => void;
  /** Modal title */
  title: string;
  /** Confirmation message */
  message: React.ReactNode;
  /** Confirm button text */
  confirmText?: string;
  /** Cancel button text */
  cancelText?: string;
  /** Confirm button variant (danger, warning, etc.) */
  variant?: 'danger' | 'warning' | 'primary';
  /** Loading state for confirm button */
  loading?: boolean;
  /** Require typing specific text to confirm */
  confirmationText?: string;
  /** Current typed confirmation value */
  confirmationValue?: string;
  /** Callback when confirmation text changes */
  onConfirmationChange?: (value: string) => void;
}

/**
 * Pre-configured confirmation modal for destructive actions.
 *
 * @example
 * <ConfirmationModal
 *   open={showDelete}
 *   onClose={() => setShowDelete(false)}
 *   onConfirm={handleDelete}
 *   title="Delete User"
 *   message="This action cannot be undone."
 *   variant="danger"
 *   confirmText="Delete"
 * />
 *
 * // With typed confirmation
 * <ConfirmationModal
 *   open={showReset}
 *   onClose={() => setShowReset(false)}
 *   onConfirm={handleReset}
 *   title="Reset All Settings"
 *   message="Type RESET to confirm"
 *   confirmationText="RESET"
 *   confirmationValue={typed}
 *   onConfirmationChange={setTyped}
 * />
 */
export function ConfirmationModal({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'primary',
  loading = false,
  confirmationText,
  confirmationValue,
  onConfirmationChange,
}: ConfirmationModalProps) {
  const headerVariant: ModalHeaderVariant =
    variant === 'danger' ? 'error' :
    variant === 'warning' ? 'warning' :
    'default';

  const buttonVariant =
    variant === 'danger' ? 'danger' :
    variant === 'warning' ? 'warning' :
    'primary';

  const canConfirm = confirmationText
    ? confirmationValue === confirmationText
    : true;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="md"
      headerVariant={headerVariant}
    >
      <div className="space-y-4">
        <div className="text-[#d4c39b]">{message}</div>

        {confirmationText && (
          <div>
            <label className="mb-2 block text-sm font-medium text-[#a89465]">
              Type <span className="font-mono text-[#fff4cc]">{confirmationText}</span> to confirm:
            </label>
            <input
              type="text"
              value={confirmationValue || ''}
              onChange={(e) => onConfirmationChange?.(e.target.value)}
              className="w-full rounded border border-[#ffbb00]/18 bg-[#120d00] px-4 py-2 text-[#fff4cc] placeholder-[#7d6c43] focus:border-[#ffbb00]/45 focus:outline-none"
              placeholder={confirmationText}
            />
          </div>
        )}
      </div>

      <ModalFooter className="-mx-6 -mb-4 mt-4 border-t border-[#ffbb00]/15 px-6 py-4">
        <button
          onClick={onClose}
          className="rounded border border-[#ffbb00]/18 bg-[#120d00] px-4 py-2 text-[#d6c7a3] transition hover:bg-[#1a1304] hover:text-[#fff1bf]"
          disabled={loading}
        >
          {cancelText}
        </button>
        <button
          onClick={onConfirm}
          disabled={!canConfirm || loading}
          className={cn(
            'px-4 py-2 rounded transition font-medium',
            buttonVariant === 'danger' && 'bg-red-900/30 hover:bg-red-900/50 text-red-200 border border-red-700 disabled:opacity-50',
            buttonVariant === 'warning' && 'bg-yellow-900/30 hover:bg-yellow-900/50 text-yellow-200 border border-yellow-700 disabled:opacity-50',
            buttonVariant === 'primary' && 'border border-[#ffbb00]/45 bg-[linear-gradient(180deg,rgba(255,187,0,0.22),rgba(255,187,0,0.12))] text-[#fff1bf] disabled:bg-[#17120a] disabled:text-[#7d6c43] hover:bg-[linear-gradient(180deg,rgba(255,187,0,0.3),rgba(255,187,0,0.16))]',
          )}
        >
          {loading ? 'Processing...' : confirmText}
        </button>
      </ModalFooter>
    </Modal>
  );
}
