/**
 * Keyboard Shortcuts Hook
 * Power user feature for hackathon impact
 */

import { useEffect } from 'react';

export interface KeyboardShortcut {
  key: string;
  ctrlKey?: boolean;
  shiftKey?: boolean;
  altKey?: boolean;
  callback: () => void;
  description: string;
}

export function useKeyboardShortcuts(shortcuts: KeyboardShortcut[]) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      for (const shortcut of shortcuts) {
        const modifierMatch = 
          (shortcut.ctrlKey === undefined || shortcut.ctrlKey === (event.ctrlKey || event.metaKey)) &&
          (shortcut.shiftKey === undefined || shortcut.shiftKey === event.shiftKey) &&
          (shortcut.altKey === undefined || shortcut.altKey === event.altKey);

        if (modifierMatch && event.key.toLowerCase() === shortcut.key.toLowerCase()) {
          event.preventDefault();
          shortcut.callback();
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);
}

// Keyboard shortcuts modal component
export const AVAILABLE_SHORTCUTS: KeyboardShortcut[] = [
  {
    key: 'k',
    ctrlKey: true,
    callback: () => {}, // Set in component
    description: 'Focus search'
  },
  {
    key: 'Enter',
    ctrlKey: true,
    callback: () => {}, // Set in component
    description: 'Start research'
  },
  {
    key: 's',
    ctrlKey: true,
    callback: () => {}, // Set in component
    description: 'Save report'
  },
  {
    key: 'e',
    ctrlKey: true,
    callback: () => {}, // Set in component
    description: 'Export report'
  },
  {
    key: '/',
    ctrlKey: true,
    callback: () => {}, // Set in component
    description: 'Show shortcuts'
  }
];
