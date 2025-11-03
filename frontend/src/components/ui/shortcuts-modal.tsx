"use client";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./dialog";
import { Keyboard } from "lucide-react";

interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ShortcutsModal({ isOpen, onClose }: ShortcutsModalProps) {
  const shortcuts = [
    { keys: ["Ctrl", "K"], description: "Focus search input" },
    { keys: ["Ctrl", "Enter"], description: "Start research" },
    { keys: ["Ctrl", "S"], description: "Save current report" },
    { keys: ["Ctrl", "E"], description: "Export report as PDF" },
    { keys: ["Ctrl", "/"], description: "Show this help" },
    { keys: ["Esc"], description: "Close dialogs" },
  ];

  const isMac = typeof window !== 'undefined' && navigator.platform.toUpperCase().indexOf('MAC') >= 0;
  const cmdKey = isMac ? "⌘" : "Ctrl";

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="bg-slate-900 border-white/20 text-white max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <Keyboard className="w-6 h-6 text-purple-400" />
            Keyboard Shortcuts
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3 mt-4">
          {shortcuts.map((shortcut, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between py-3 px-4 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
            >
              <span className="text-white/90">{shortcut.description}</span>
              <div className="flex items-center gap-1">
                {shortcut.keys.map((key, keyIdx) => (
                  <kbd
                    key={keyIdx}
                    className="px-3 py-1.5 bg-white/20 rounded text-xs font-mono text-white border border-white/30"
                  >
                    {key === "Ctrl" ? cmdKey : key}
                  </kbd>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <p className="text-sm text-blue-300">
            <strong>Tip:</strong> Press <kbd className="px-2 py-1 bg-blue-500/20 rounded text-xs mx-1">{cmdKey}/</kbd> 
            anytime to view shortcuts
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
