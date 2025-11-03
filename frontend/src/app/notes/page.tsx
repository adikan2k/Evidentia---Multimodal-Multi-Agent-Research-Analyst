"use client";

import { useState, useEffect } from "react";
import { GlassCard } from "@/components/ui/glass-card";
import { AnimatedGradientBg } from "@/components/ui/animated-gradient-bg";
import { GradientButton } from "@/components/ui/gradient-button";
import { Footer } from "@/components/ui/footer";
import { 
  FileText, 
  Trash2, 
  Download, 
  Plus, 
  Save,
  Edit3,
  X,
  Check,
  Clock,
  Hash
} from "lucide-react";
import Link from "next/link";

interface Note {
  id: string;
  title: string;
  content: string;
  createdAt: string;
  updatedAt: string;
}

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [currentNote, setCurrentNote] = useState<Note | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  // Load notes from localStorage on mount
  useEffect(() => {
    const savedNotes = localStorage.getItem("evidentia-notes");
    if (savedNotes) {
      setNotes(JSON.parse(savedNotes));
    }
  }, []);

  // Save notes to localStorage whenever they change
  useEffect(() => {
    if (notes.length > 0) {
      localStorage.setItem("evidentia-notes", JSON.stringify(notes));
    }
  }, [notes]);

  const createNewNote = () => {
    const newNote: Note = {
      id: Date.now().toString(),
      title: "New Note",
      content: "",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
    setNotes([newNote, ...notes]);
    setCurrentNote(newNote);
    setTitle(newNote.title);
    setContent(newNote.content);
    setIsEditing(true);
  };

  const selectNote = (note: Note) => {
    setCurrentNote(note);
    setTitle(note.title);
    setContent(note.content);
    setIsEditing(false);
  };

  const saveNote = () => {
    if (!currentNote) return;

    const updatedNote: Note = {
      ...currentNote,
      title: title.trim() || "Untitled Note",
      content: content.trim(),
      updatedAt: new Date().toISOString()
    };

    setNotes(notes.map(note => 
      note.id === currentNote.id ? updatedNote : note
    ));
    setCurrentNote(updatedNote);
    setIsEditing(false);
  };

  const deleteNote = (noteId: string) => {
    setNotes(notes.filter(note => note.id !== noteId));
    if (currentNote?.id === noteId) {
      setCurrentNote(null);
      setTitle("");
      setContent("");
    }
  };

  const exportNotes = () => {
    const dataStr = JSON.stringify(notes, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = `evidentia-notes-${new Date().toISOString().split('T')[0]}.json`;
    
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const wordCount = content.trim().split(/\s+/).filter(word => word.length > 0).length;

  return (
    <AnimatedGradientBg>
      <div className="min-h-screen">
        {/* Header */}
        <header className="border-b border-white/10 backdrop-blur-sm bg-white/5">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <Link href="/" className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                  <FileText className="w-5 h-5 text-white" />
                </div>
                <span className="text-xl font-bold text-white">Evidentia Notes</span>
              </Link>
              <div className="flex items-center space-x-3">
                <GradientButton 
                  variant="outline" 
                  size="sm" 
                  onClick={exportNotes}
                  disabled={notes.length === 0}
                >
                  <Download className="w-4 h-4 mr-2" />
                  Export
                </GradientButton>
                <Link href="/">
                  <GradientButton variant="outline" size="sm">
                    Back to Research
                  </GradientButton>
                </Link>
              </div>
            </div>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid lg:grid-cols-3 gap-6">
            {/* Notes List */}
            <div className="lg:col-span-1">
              <GlassCard className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-xl font-semibold text-white">My Notes</h3>
                  <GradientButton size="sm" onClick={createNewNote}>
                    <Plus className="w-4 h-4 mr-2" />
                    New
                  </GradientButton>
                </div>

                {notes.length === 0 ? (
                  <div className="text-center py-12">
                    <FileText className="w-12 h-12 text-white/30 mx-auto mb-4" />
                    <p className="text-white/60 mb-4">No notes yet</p>
                    <GradientButton size="sm" onClick={createNewNote}>
                      Create your first note
                    </GradientButton>
                  </div>
                ) : (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {notes.map((note) => (
                      <div
                        key={note.id}
                        className={`p-4 rounded-lg border cursor-pointer transition-all ${
                          currentNote?.id === note.id
                            ? "bg-blue-500/20 border-blue-500/40"
                            : "bg-white/5 border-white/10 hover:bg-white/10 hover:border-white/20"
                        }`}
                        onClick={() => selectNote(note)}
                      >
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="font-medium text-white truncate flex-1">
                            {note.title}
                          </h4>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteNote(note.id);
                            }}
                            className="text-white/40 hover:text-red-400 transition-colors ml-2"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                        <p className="text-white/60 text-sm line-clamp-2 mb-2">
                          {note.content || "Empty note"}
                        </p>
                        <div className="flex items-center text-xs text-white/40">
                          <Clock className="w-3 h-3 mr-1" />
                          {formatDate(note.updatedAt)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </GlassCard>
            </div>

            {/* Note Editor */}
            <div className="lg:col-span-2">
              {currentNote ? (
                <GlassCard className="p-6">
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex-1">
                      {isEditing ? (
                        <input
                          type="text"
                          value={title}
                          onChange={(e) => setTitle(e.target.value)}
                          className="text-2xl font-bold text-white bg-transparent border-b border-white/20 focus:border-blue-400 outline-none w-full"
                          placeholder="Note title..."
                        />
                      ) : (
                        <h2 className="text-2xl font-bold text-white">{title}</h2>
                      )}
                    </div>
                    <div className="flex items-center space-x-2 ml-4">
                      {isEditing ? (
                        <>
                          <GradientButton size="sm" onClick={saveNote}>
                            <Save className="w-4 h-4 mr-2" />
                            Save
                          </GradientButton>
                          <GradientButton 
                            variant="outline" 
                            size="sm" 
                            onClick={() => {
                              setIsEditing(false);
                              setTitle(currentNote.title);
                              setContent(currentNote.content);
                            }}
                          >
                            <X className="w-4 h-4 mr-2" />
                            Cancel
                          </GradientButton>
                        </>
                      ) : (
                        <GradientButton size="sm" onClick={() => setIsEditing(true)}>
                          <Edit3 className="w-4 h-4 mr-2" />
                          Edit
                        </GradientButton>
                      )}
                    </div>
                  </div>

                  <div className="mb-4">
                    <div className="flex items-center text-sm text-white/60 space-x-4">
                      <div className="flex items-center">
                        <Hash className="w-3 h-3 mr-1" />
                        {wordCount} words
                      </div>
                      <div className="flex items-center">
                        <Clock className="w-3 h-3 mr-1" />
                        Updated {formatDate(currentNote.updatedAt)}
                      </div>
                    </div>
                  </div>

                  {isEditing ? (
                    <textarea
                      value={content}
                      onChange={(e) => setContent(e.target.value)}
                      className="w-full h-96 bg-white/5 border border-white/10 rounded-lg p-4 text-white/90 placeholder-white/40 focus:border-blue-400 focus:outline-none resize-none"
                      placeholder="Start typing your notes here..."
                    />
                  ) : (
                    <div className="bg-white/5 border border-white/10 rounded-lg p-4 min-h-96">
                      <p className="text-white/90 whitespace-pre-wrap">
                        {content || "No content yet. Click Edit to start writing."}
                      </p>
                    </div>
                  )}
                </GlassCard>
              ) : (
                <GlassCard className="p-12 text-center">
                  <FileText className="w-16 h-16 text-white/30 mx-auto mb-4" />
                  <h3 className="text-xl font-semibold text-white mb-2">Select a note to view</h3>
                  <p className="text-white/60 mb-6">Choose a note from the list or create a new one</p>
                  <GradientButton onClick={createNewNote}>
                    <Plus className="w-4 h-4 mr-2" />
                    Create New Note
                  </GradientButton>
                </GlassCard>
              )}
            </div>
          </div>
        </main>
        <Footer />
      </div>
    </AnimatedGradientBg>
  );
}
