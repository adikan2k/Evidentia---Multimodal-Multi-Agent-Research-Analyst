"use client";

import { LightbulbIcon, TrendingUp, Code, Heart, Zap, Brain } from "lucide-react";

interface QuerySuggestionsProps {
  onSelect: (query: string) => void;
  visible?: boolean;
}

const EXAMPLE_QUERIES = [
  {
    category: "Technology",
    icon: Code,
    color: "blue",
    queries: [
      "GPT-4 vs Claude 3 Opus for coding assistance",
      "React vs Vue 2024 performance comparison",
      "Best practices for TypeScript in 2024",
      "Rust vs Go for systems programming"
    ]
  },
  {
    category: "AI & ML",
    icon: Brain,
    color: "purple",
    queries: [
      "Transformer architecture explained",
      "Fine-tuning vs RAG for custom AI applications",
      "Open source LLM alternatives to ChatGPT",
      "AI safety and alignment challenges"
    ]
  },
  {
    category: "Health",
    icon: Heart,
    color: "red",
    queries: [
      "Benefits of intermittent fasting backed by science",
      "Mental health impact of social media",
      "Latest treatments for Type 2 diabetes",
      "Sleep quality improvement strategies"
    ]
  },
  {
    category: "Trending",
    icon: TrendingUp,
    color: "green",
    queries: [
      "AI trends and predictions for 2024",
      "Climate change solutions that actually work",
      "Web3 and blockchain real-world applications",
      "Future of remote work and productivity"
    ]
  }
];

export function QuerySuggestions({ onSelect, visible = true }: QuerySuggestionsProps) {
  if (!visible) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-white/80">
        <LightbulbIcon className="w-5 h-5 text-yellow-400" />
        <span className="font-medium">Popular Research Topics</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {EXAMPLE_QUERIES.map((category) => {
          const Icon = category.icon;
          const colorClasses = {
            blue: "from-blue-500/20 to-blue-600/20 border-blue-500/30 hover:border-blue-400/50",
            purple: "from-purple-500/20 to-purple-600/20 border-purple-500/30 hover:border-purple-400/50",
            red: "from-red-500/20 to-red-600/20 border-red-500/30 hover:border-red-400/50",
            green: "from-green-500/20 to-green-600/20 border-green-500/30 hover:border-green-400/50"
          }[category.color];

          return (
            <div
              key={category.category}
              className={`bg-gradient-to-br ${colorClasses} border rounded-xl p-5 transition-all duration-300 hover:scale-[1.02]`}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className={`p-2 rounded-lg bg-white/10`}>
                  <Icon className="w-5 h-5 text-white" />
                </div>
                <h3 className="font-semibold text-white">{category.category}</h3>
              </div>

              <div className="space-y-2">
                {category.queries.map((query, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSelect(query)}
                    className="w-full text-left px-3 py-2 rounded-lg bg-white/5 hover:bg-white/15 text-white/90 text-sm transition-all duration-200 hover:translate-x-1 group"
                  >
                    <div className="flex items-center gap-2">
                      <Zap className="w-3 h-3 text-yellow-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                      <span className="line-clamp-1">{query}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Inline search suggestions (as user types)
export function InlineSuggestions({ query, onSelect }: { query: string; onSelect: (query: string) => void }) {
  if (!query || query.length < 3) return null;

  const allQueries = EXAMPLE_QUERIES.flatMap(cat => cat.queries);
  const matches = allQueries.filter(q => 
    q.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 5);

  if (matches.length === 0) return null;

  return (
    <div className="absolute top-full left-0 right-0 mt-2 bg-slate-900/95 backdrop-blur-lg border border-white/20 rounded-lg shadow-xl z-50 overflow-hidden">
      {matches.map((match, idx) => (
        <button
          key={idx}
          onClick={() => onSelect(match)}
          className="w-full text-left px-4 py-3 hover:bg-white/10 text-white/90 text-sm transition-colors border-b border-white/10 last:border-0"
        >
          <div className="flex items-center gap-2">
            <LightbulbIcon className="w-4 h-4 text-yellow-400 flex-shrink-0" />
            <span>{match}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
