-- Add category-level role prerequisite fields for ticket creation eligibility.

ALTER TABLE ticket_categories
ADD COLUMN prerequisite_role_ids_all TEXT NOT NULL DEFAULT '[]';

ALTER TABLE ticket_categories
ADD COLUMN prerequisite_role_ids_any TEXT NOT NULL DEFAULT '[]';
