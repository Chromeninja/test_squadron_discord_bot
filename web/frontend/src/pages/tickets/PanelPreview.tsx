/**
 * PanelPreview — Display a live preview of a Discord embed panel
 *
 * Shows how the ticket panel will appear in Discord with the
 * current title, description, color, and button configuration.
 */

import React from 'react';

interface PanelPreviewProps {
  title: string;
  description: string;
  color: string;
  buttonText: string;
  buttonEmoji?: string | null;
  enablePublicButton?: boolean;
  publicButtonText?: string;
  publicButtonEmoji?: string | null;
  privateButtonColor?: string | null;
  publicButtonColor?: string | null;
  buttonOrder?: string;
}

// Map hex colors to Discord button styles (background colors)
const getButtonBgColor = (hexColor: string | null | undefined, defaultColor: string): string => {
  if (!hexColor) return defaultColor;
  
  const normalized = hexColor.trim().toUpperCase().replace('#', '');
  
  // Blue/Blurple (Primary)
  if (['5865F2', '5865F3', '5865F4', '0099FF', '3B88F3'].includes(normalized)) {
    return '#5865f2';
  }
  // Gray (Secondary)
  if (['4E5058', '4F545C', '6C757D', '2C2F33'].includes(normalized)) {
    return '#4f545c';
  }
  // Green (Success)
  if (['3BA55D', '57F287', '43B581', '00C853'].includes(normalized)) {
    return '#3ba55d';
  }
  // Red (Danger)
  if (['ED4245', 'F04747', 'D32F2F', 'E74C3C'].includes(normalized)) {
    return '#ed4245';
  }
  
  return defaultColor;
};

export const PanelPreview: React.FC<PanelPreviewProps> = ({
  title,
  description,
  color,
  buttonText,
  buttonEmoji,
  enablePublicButton = false,
  publicButtonText = 'Create Public Ticket',
  publicButtonEmoji = '🌐',
  privateButtonColor,
  publicButtonColor,
  buttonOrder = 'private_first',
}) => {
  // Convert hex color string to CSS color
  const borderColor = color.startsWith('#') ? color : `#${color}`;
  
  // Get button background colors
  const privateBg = getButtonBgColor(privateButtonColor, '#5865f2');
  const publicBg = getButtonBgColor(publicButtonColor, '#4f545c');

  // Create button elements
  const privateButton = (
    <button
      key="private"
      type="button"
      className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium text-white transition-colors cursor-default"
      style={{ backgroundColor: privateBg }}
    >
      {buttonEmoji && <span>{buttonEmoji}</span>}
      {buttonText}
    </button>
  );

  const publicButton = enablePublicButton ? (
    <button
      key="public"
      type="button"
      className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium text-white cursor-default"
      style={{ backgroundColor: publicBg }}
    >
      {publicButtonEmoji && <span>{publicButtonEmoji}</span>}
      {publicButtonText}
    </button>
  ) : null;

  // Determine button order
  const buttons = buttonOrder === 'public_first' && publicButton
    ? [publicButton, privateButton]
    : publicButton
    ? [privateButton, publicButton]
    : [privateButton];

  return (
    <div
      className="rounded bg-[#2b2d31] p-4 max-w-[600px]"
      style={{ borderLeft: `4px solid ${borderColor}` }}
    >
      {/* Embed Title */}
      {title && (
        <p className="text-white font-semibold mb-1">{title}</p>
      )}

      {/* Embed Description */}
      {description && (
        <p className="text-[#b5bac1] text-sm whitespace-pre-wrap mb-3">
          {description}
        </p>
      )}

      {/* Button Preview */}
      <div className="flex flex-wrap items-center gap-2">
        {buttons}
      </div>
    </div>
  );
};
