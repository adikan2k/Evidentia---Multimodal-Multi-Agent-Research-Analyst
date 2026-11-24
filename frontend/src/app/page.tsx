"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

// shadcn/ui components
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

// Custom components
import { GlassCard } from "@/components/ui/glass-card";
import { GradientButton } from "@/components/ui/gradient-button";
import { AnimatedGradientBg } from "@/components/ui/animated-gradient-bg";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";
import { Footer } from "@/components/ui/footer";
import { VoiceInput } from "@/components/ui/voice-input";

import { toast } from "sonner";
import { Search, Zap, BookOpen, TrendingUp, Users, BarChart3, Keyboard } from "lucide-react";

import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import { ShortcutsModal } from "@/components/ui/shortcuts-modal";
import { QuerySuggestions } from "@/components/ui/query-suggestions";

export default function AskPage() {
  const [q, setQ] = useState("");
  const [recent, setRecent] = useState(true);
  const [includeYoutube, setIncludeYoutube] = useState(true);
  const [maxSources, setMaxSources] = useState(12);
  const [loading, setLoading] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const router = useRouter();
  const queryInputRef = useRef<HTMLTextAreaElement>(null);

  // Keyboard shortcuts
  useKeyboardShortcuts([
    {
      key: 'k',
      ctrlKey: true,
      callback: () => queryInputRef.current?.focus(),
      description: 'Focus search'
    },
    {
      key: 'Enter',
      ctrlKey: true,
      callback: () => {
        if (q.trim()) startResearch();
      },
      description: 'Start research'
    },
    {
      key: '/',
      ctrlKey: true,
      callback: () => setShowShortcuts(true),
      description: 'Show shortcuts'
    }
  ]);

  const [popularTopics, setPopularTopics] = useState([
    "Latest AI developments in healthcare",
    "Climate change solutions 2024",
    "Quantum computing breakthroughs",
    "Renewable energy innovations",
    "Space exploration milestones",
    "Biotechnology advances"
  ]);

  async function startResearch() {
    if (!q.trim()) return toast.error("Please enter a research question");
    setLoading(true);
    try {
      const resp = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/research/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, options: { recent, includeYoutube, maxSources } }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      toast.success("Research started");
      router.push(`/research/progress?jobId=${data.job_id}`);
    } catch (e) {
      console.error(e);
      toast.error("Failed to start research");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AnimatedGradientBg>
      <div className="min-h-screen flex flex-col">
        {/* Header */}
        <header className="border-b border-white/10 backdrop-blur-sm bg-white/5">
          <div className="container mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl flex items-center justify-center">
                  <Search className="w-6 h-6 text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">Evidentia</h1>
              </div>
              <nav className="flex items-center space-x-6">
                <Link href="/about" className="text-white/80 hover:text-white transition-colors">About</Link>
                <Link href="/notes" className="text-white/80 hover:text-white transition-colors">Notes</Link>
                <button
                  onClick={() => setShowShortcuts(true)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-all duration-200 border border-white/10 hover:border-white/30"
                >
                  <Keyboard className="w-4 h-4" />
                  <span className="text-sm">Shortcuts</span>
                </button>
              </nav>
            </div>
          </div>
        </header>

        {/* Hero Section */}
        <main className="flex-1 container mx-auto px-6 py-12">
          <div className="max-w-6xl mx-auto">
            {/* Popular Topics - Moved Up */}
            <GlassCard className="p-6 mb-8">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-white font-semibold flex items-center">
                  <Zap className="w-5 h-5 mr-2 text-yellow-400 animate-pulse" />
                  Example topics
                </h3>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {popularTopics.map((topic, index) => (
                  <button
                    key={index}
                    onClick={() => {
                      setQ(topic);
                      toast.success("Topic loaded! Click 'Start Research' to begin.");
                    }}
                    className="text-left p-3 bg-white/5 rounded-lg border border-white/10 hover:bg-white/10 hover:border-blue-400/30 transition-all duration-300 group"
                  >
                    <span className="text-white/80 group-hover:text-white text-sm">
                      {topic}
                    </span>
                  </button>
                ))}
              </div>
            </GlassCard>

            <div className="text-center mb-12">
              <h2 className="text-5xl md:text-6xl font-bold text-white mb-6">
                Research Anything.
                <br />
                <span className="bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
                  Get Evidence-Based Answers.
                </span>
              </h2>
              <p className="text-xl text-white/80 mb-8 max-w-2xl mx-auto">
                Data science-powered research platform that leverages AI and machine learning 
                to analyze multiple sources, extract insights, and generate comprehensive reports with citations.
              </p>
            </div>

            {/* Query Suggestions - Show when empty */}
            {showSuggestions && !q && (
              <div className="mb-8">
                <QuerySuggestions 
                  onSelect={(query) => {
                    setQ(query);
                    setShowSuggestions(false);
                  }}
                />
              </div>
            )}

            {/* Main Content */}
            <div className="max-w-3xl mx-auto">
              {/* Research Form */}
              <div className="space-y-6">
                <GlassCard variant="strong" className="p-8">
                  <div className="space-y-6">
                    <div>
                      <Label htmlFor="q" className="text-white text-lg font-semibold mb-3 block">
                        What would you like to research?
                      </Label>
                      <Textarea
                        ref={queryInputRef}
                        id="q"
                        placeholder="e.g., Compare GLP-1 vs SGLT2 outcomes in Type 2 Diabetes treatment..."
                        value={q}
                        onChange={(e) => {
                          setQ(e.target.value);
                          setShowSuggestions(false);
                        }}
                        onKeyDown={(e) => (e.key === "Enter" && (e.metaKey || e.ctrlKey)) && startResearch()}
                        className="min-h-[140px] bg-white/10 border-white/20 text-white placeholder:text-white/50 resize-none focus:border-blue-400 transition-colors"
                      />
                      <div className="flex items-center justify-between mt-2">
                        <div className="text-xs text-white/60 flex items-center">
                          <kbd className="px-2 py-1 bg-white/10 rounded text-xs mr-2">Ctrl</kbd>
                          <span>+</span>
                          <kbd className="px-2 py-1 bg-white/10 rounded text-xs mx-2">Enter</kbd>
                          <span>to submit</span>
                        </div>
                        <VoiceInput 
                          onTranscript={(text) => {
                            setQ(prev => {
                              // If query is empty, just set the text
                              if (!prev || prev.trim() === "") return text;
                              // If there's existing text, append with space
                              return prev.trim() + " " + text.trim();
                            });
                          }}
                          language="en-US"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-3">
                        <Label className="text-white font-medium">Max sources</Label>
                        <Input
                          type="number"
                          min={1}
                          max={50}
                          value={maxSources}
                          onChange={(e) => setMaxSources(+e.target.value)}
                          className="bg-white/10 border-white/20 text-white focus:border-blue-400 transition-colors"
                        />
                      </div>

                      <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/10">
                        <div>
                          <div className="text-sm font-medium text-white">Prefer recent</div>
                          <div className="text-xs text-white/60">Bias towards newer sources</div>
                        </div>
                        <Switch 
                          checked={recent} 
                          onCheckedChange={setRecent}
                          className="data-[state=checked]:bg-blue-500"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/10">
                      <div>
                        <div className="text-sm font-medium text-white">Include YouTube</div>
                        <div className="text-xs text-white/60">Transcribe + cite videos</div>
                      </div>
                      <Switch 
                        checked={includeYoutube} 
                        onCheckedChange={setIncludeYoutube}
                        className="data-[state=checked]:bg-blue-500"
                      />
                    </div>

                    <GradientButton 
                      size="lg" 
                      className="w-full text-lg py-4"
                      onClick={startResearch} 
                      disabled={!q || loading}
                    >
                      {loading ? (
                        <div className="flex items-center space-x-3">
                          <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          <span>Analyzing sources...</span>
                        </div>
                      ) : (
                        <div className="flex items-center space-x-3">
                          <Search className="w-5 h-5" />
                          <span>Start Research</span>
                        </div>
                      )}
                    </GradientButton>
                  </div>
                </GlassCard>

                {/* Features Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <GlassCard className="p-6 text-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl flex items-center justify-center mx-auto mb-3">
                      <BookOpen className="w-6 h-6 text-white" />
                    </div>
                    <h3 className="text-white font-semibold mb-2">Multimodal Analysis</h3>
                    <p className="text-white/60 text-sm">Text, PDFs, videos, and images</p>
                  </GlassCard>
                  
                  <GlassCard className="p-6 text-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center mx-auto mb-3">
                      <BarChart3 className="w-6 h-6 text-white" />
                    </div>
                    <h3 className="text-white font-semibold mb-2">Evidence Matrix</h3>
                    <p className="text-white/60 text-sm">Citation-backed insights</p>
                  </GlassCard>
                  
                  <GlassCard className="p-6 text-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-green-500 to-emerald-500 rounded-xl flex items-center justify-center mx-auto mb-3">
                      <Users className="w-6 h-6 text-white" />
                    </div>
                    <h3 className="text-white font-semibold mb-2">Export & Share</h3>
                    <p className="text-white/60 text-sm">PDF, JSON, CSV formats</p>
                  </GlassCard>
                </div>
              </div>
            </div>
          </div>
        </main>
        <Footer />
      </div>

      {/* Shortcuts Modal */}
      <ShortcutsModal 
        isOpen={showShortcuts}
        onClose={() => setShowShortcuts(false)}
      />
    </AnimatedGradientBg>
  );
}
