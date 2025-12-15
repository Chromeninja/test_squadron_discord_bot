/**
 * UI Component Library
 * 
 * Centralized exports for all reusable UI components.
 * Import from this file rather than individual component files.
 * 
 * @example
 * import { Button, Badge, Card, Modal, Alert, Table } from '@/components/ui';
 */

// Atomic Components
export { Button, type ButtonProps } from './Button';
export { Badge, StatusBadge, MembershipBadge, type BadgeProps, type StatusBadgeProps, type MembershipBadgeProps } from './Badge';
export { Input, Textarea, type InputProps, type TextareaProps } from './Input';

// Container Components
export { Card, CardHeader, CardBody, CardFooter, CollapsibleCard, type CardProps, type CardHeaderProps, type CardBodyProps, type CardFooterProps, type CollapsibleCardProps } from './Card';
export { Alert, Banner, type AlertProps, type BannerProps } from './Alert';
export { Modal, ModalHeader, ModalBody, ModalFooter, ConfirmationModal, type ModalProps, type ModalHeaderProps, type ModalBodyProps, type ModalFooterProps, type ConfirmationModalProps } from './Modal';
export { Table, TableHead, TableBody, TableRow, TableHeader, TableCell, TableEmpty, DataTable, type TableProps, type TableHeadProps, type TableBodyProps, type TableRowProps, type TableHeaderProps, type TableCellProps, type TableEmptyProps, type DataTableProps, type Column } from './Table';
