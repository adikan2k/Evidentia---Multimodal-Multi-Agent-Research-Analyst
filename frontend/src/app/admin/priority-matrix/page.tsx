"use client";

import { useState } from "react";
import { GlassCard } from "@/components/ui/glass-card";
import { AnimatedGradientBg } from "@/components/ui/animated-gradient-bg";
import { Badge } from "@/components/ui/badge";
import { Brain, TrendingUp, Zap, Target, Clock, DollarSign } from "lucide-react";

interface Feature {
  id: string;
  name: string;
  description: string;
  impact: number; // 1-10
  effort: number; // 1-10 (1 = easy, 10 = hard)
  priority: string;
  status: string;
  estimatedTime: string;
  roi: number;
  dependencies: string[];
}

export default function PriorityMatrixPage() {
  const [features] = useState<Feature[]>([
    {
      id: "1",
      name: "Citation Management",
      description: "Multiple citation formats (APA, MLA, Chicago, Harvard, IEEE, Vancouver)",
      impact: 9,
      effort: 3,
      priority: "P0",
      status: "Completed",
      estimatedTime: "1 week",
      roi: 9.5,
      dependencies: []
    },
    {
      id: "2",
      name: "Research Templates",
      description: "Pre-built templates for different research types",
      impact: 8,
      effort: 2,
      priority: "P0",
      status: "Completed",
      estimatedTime: "3 days",
      roi: 9.0,
      dependencies: []
    },
    {
      id: "3",
      name: "Multi-Language Support",
      description: "Automatic translation and language detection",
      impact: 10,
      effort: 7,
      priority: "P1",
      status: "Completed",
      estimatedTime: "2 weeks",
      roi: 8.5,
      dependencies: []
    },
    {
      id: "4",
      name: "AI Fact-Checking",
      description: "Verify claims against multiple sources with confidence scores",
      impact: 10,
      effort: 6,
      priority: "P1",
      status: "Completed",
      estimatedTime: "2 weeks",
      roi: 9.0,
      dependencies: []
    },
    {
      id: "5",
      name: "Source Credibility Scoring",
      description: "Rate sources by authority and reliability",
      impact: 9,
      effort: 5,
      priority: "P1",
      status: "Completed",
      estimatedTime: "1.5 weeks",
      roi: 8.8,
      dependencies: []
    },
    {
      id: "6",
      name: "Visual Data Extraction",
      description: "Extract and analyze charts, graphs, and tables",
      impact: 8,
      effort: 8,
      priority: "P2",
      status: "Completed",
      estimatedTime: "3 weeks",
      roi: 7.5,
      dependencies: []
    },
    {
      id: "7",
      name: "Voice Input",
      description: "Voice-to-text for queries using Web Speech API",
      impact: 7,
      effort: 3,
      priority: "P1",
      status: "Completed",
      estimatedTime: "1 week",
      roi: 8.0,
      dependencies: []
    },
    {
      id: "8",
      name: "Dark Mode Toggle",
      description: "User preference for dark/light theme",
      impact: 6,
      effort: 2,
      priority: "P0",
      status: "Pending",
      estimatedTime: "2 hours",
      roi: 7.0,
      dependencies: []
    },
    {
      id: "9",
      name: "Real-Time Collaboration",
      description: "Multiple users collaborate on research projects",
      impact: 10,
      effort: 10,
      priority: "P2",
      status: "Pending",
      estimatedTime: "6 weeks",
      roi: 8.0,
      dependencies: ["WebSocket", "Auth"]
    },
    {
      id: "10",
      name: "Mobile App",
      description: "Native iOS/Android applications",
      impact: 8,
      effort: 10,
      priority: "P3",
      status: "Pending",
      estimatedTime: "12 weeks",
      roi: 7.0,
      dependencies: ["API", "Auth"]
    }
  ]);

  const getQuadrant = (impact: number, effort: number) => {
    if (impact >= 7 && effort <= 5) return "quick-wins";
    if (impact >= 7 && effort > 5) return "major-projects";
    if (impact < 7 && effort <= 5) return "fill-ins";
    return "time-sinks";
  };

  const quadrants = {
    "quick-wins": features.filter(f => getQuadrant(f.impact, f.effort) === "quick-wins"),
    "major-projects": features.filter(f => getQuadrant(f.impact, f.effort) === "major-projects"),
    "fill-ins": features.filter(f => getQuadrant(f.impact, f.effort) === "fill-ins"),
    "time-sinks": features.filter(f => getQuadrant(f.impact, f.effort) === "time-sinks")
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case "P0": return "bg-red-500/20 text-red-400 border-red-500/30";
      case "P1": return "bg-orange-500/20 text-orange-400 border-orange-500/30";
      case "P2": return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
      case "P3": return "bg-blue-500/20 text-blue-400 border-blue-500/30";
      default: return "bg-gray-500/20 text-gray-400 border-gray-500/30";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "Completed": return "bg-green-500/20 text-green-400 border-green-500/30";
      case "In Progress": return "bg-blue-500/20 text-blue-400 border-blue-500/30";
      case "Pending": return "bg-gray-500/20 text-gray-400 border-gray-500/30";
      default: return "bg-gray-500/20 text-gray-400 border-gray-500/30";
    }
  };

  const completedFeatures = features.filter(f => f.status === "Completed");
  const avgImpact = (features.reduce((sum, f) => sum + f.impact, 0) / features.length).toFixed(1);
  const avgEffort = (features.reduce((sum, f) => sum + f.effort, 0) / features.length).toFixed(1);
  const avgROI = (features.reduce((sum, f) => sum + f.roi, 0) / features.length).toFixed(1);

  return (
    <AnimatedGradientBg>
      <div className="min-h-screen flex flex-col">
        {/* Header */}
        <header className="border-b border-white/10 backdrop-blur-sm bg-white/5">
          <div className="container mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center">
                  <Target className="w-6 h-6 text-white" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-white">Priority Matrix</h1>
                  <p className="text-sm text-white/60">Feature Impact vs. Effort Analysis</p>
                </div>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 container mx-auto px-6 py-12">
          <div className="max-w-7xl mx-auto space-y-8">
            {/* Stats Overview */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-green-400 mb-2">{completedFeatures.length}/{features.length}</div>
                <p className="text-white/60 text-sm">Features Completed</p>
              </GlassCard>
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-blue-400 mb-2">{avgImpact}/10</div>
                <p className="text-white/60 text-sm">Avg Impact Score</p>
              </GlassCard>
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-orange-400 mb-2">{avgEffort}/10</div>
                <p className="text-white/60 text-sm">Avg Effort Score</p>
              </GlassCard>
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-purple-400 mb-2">{avgROI}/10</div>
                <p className="text-white/60 text-sm">Avg ROI Score</p>
              </GlassCard>
            </div>

            {/* Priority Matrix */}
            <GlassCard variant="subtle" className="p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center">
                <Target className="w-6 h-6 mr-3 text-purple-400" />
                Impact vs. Effort Matrix
              </h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Quick Wins */}
                <div className="bg-green-500/10 border-2 border-green-500/30 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold text-green-400 flex items-center">
                      <Zap className="w-5 h-5 mr-2" />
                      Quick Wins
                    </h3>
                    <Badge className="bg-green-500/20 text-green-400 border-green-500/30">
                      High Impact, Low Effort
                    </Badge>
                  </div>
                  <div className="space-y-3">
                    {quadrants["quick-wins"].map(feature => (
                      <div key={feature.id} className="bg-white/5 rounded-lg p-4 border border-white/10">
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="font-semibold text-white">{feature.name}</h4>
                          <Badge className={getStatusColor(feature.status)}>{feature.status}</Badge>
                        </div>
                        <p className="text-sm text-white/70 mb-2">{feature.description}</p>
                        <div className="flex items-center gap-4 text-xs text-white/60">
                          <span className="flex items-center">
                            <TrendingUp className="w-3 h-3 mr-1" />
                            Impact: {feature.impact}/10
                          </span>
                          <span className="flex items-center">
                            <Clock className="w-3 h-3 mr-1" />
                            {feature.estimatedTime}
                          </span>
                          <span className="flex items-center">
                            <DollarSign className="w-3 h-3 mr-1" />
                            ROI: {feature.roi}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Major Projects */}
                <div className="bg-blue-500/10 border-2 border-blue-500/30 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold text-blue-400 flex items-center">
                      <Target className="w-5 h-5 mr-2" />
                      Major Projects
                    </h3>
                    <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">
                      High Impact, High Effort
                    </Badge>
                  </div>
                  <div className="space-y-3">
                    {quadrants["major-projects"].map(feature => (
                      <div key={feature.id} className="bg-white/5 rounded-lg p-4 border border-white/10">
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="font-semibold text-white">{feature.name}</h4>
                          <Badge className={getStatusColor(feature.status)}>{feature.status}</Badge>
                        </div>
                        <p className="text-sm text-white/70 mb-2">{feature.description}</p>
                        <div className="flex items-center gap-4 text-xs text-white/60">
                          <span className="flex items-center">
                            <TrendingUp className="w-3 h-3 mr-1" />
                            Impact: {feature.impact}/10
                          </span>
                          <span className="flex items-center">
                            <Clock className="w-3 h-3 mr-1" />
                            {feature.estimatedTime}
                          </span>
                          <span className="flex items-center">
                            <DollarSign className="w-3 h-3 mr-1" />
                            ROI: {feature.roi}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Fill-Ins */}
                <div className="bg-yellow-500/10 border-2 border-yellow-500/30 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold text-yellow-400 flex items-center">
                      <Brain className="w-5 h-5 mr-2" />
                      Fill-Ins
                    </h3>
                    <Badge className="bg-yellow-500/20 text-yellow-400 border-yellow-500/30">
                      Low Impact, Low Effort
                    </Badge>
                  </div>
                  <div className="space-y-3">
                    {quadrants["fill-ins"].map(feature => (
                      <div key={feature.id} className="bg-white/5 rounded-lg p-4 border border-white/10">
                        <div className="flex items-start justify-between mb-2">
                          <h4 className="font-semibold text-white">{feature.name}</h4>
                          <Badge className={getStatusColor(feature.status)}>{feature.status}</Badge>
                        </div>
                        <p className="text-sm text-white/70 mb-2">{feature.description}</p>
                        <div className="flex items-center gap-4 text-xs text-white/60">
                          <span className="flex items-center">
                            <TrendingUp className="w-3 h-3 mr-1" />
                            Impact: {feature.impact}/10
                          </span>
                          <span className="flex items-center">
                            <Clock className="w-3 h-3 mr-1" />
                            {feature.estimatedTime}
                          </span>
                          <span className="flex items-center">
                            <DollarSign className="w-3 h-3 mr-1" />
                            ROI: {feature.roi}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Time Sinks */}
                <div className="bg-red-500/10 border-2 border-red-500/30 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold text-red-400 flex items-center">
                      <Clock className="w-5 h-5 mr-2" />
                      Time Sinks
                    </h3>
                    <Badge className="bg-red-500/20 text-red-400 border-red-500/30">
                      Low Impact, High Effort
                    </Badge>
                  </div>
                  <div className="space-y-3">
                    {quadrants["time-sinks"].length > 0 ? (
                      quadrants["time-sinks"].map(feature => (
                        <div key={feature.id} className="bg-white/5 rounded-lg p-4 border border-white/10">
                          <div className="flex items-start justify-between mb-2">
                            <h4 className="font-semibold text-white">{feature.name}</h4>
                            <Badge className={getStatusColor(feature.status)}>{feature.status}</Badge>
                          </div>
                          <p className="text-sm text-white/70 mb-2">{feature.description}</p>
                          <div className="flex items-center gap-4 text-xs text-white/60">
                            <span className="flex items-center">
                              <TrendingUp className="w-3 h-3 mr-1" />
                              Impact: {feature.impact}/10
                            </span>
                            <span className="flex items-center">
                              <Clock className="w-3 h-3 mr-1" />
                              {feature.estimatedTime}
                            </span>
                            <span className="flex items-center">
                              <DollarSign className="w-3 h-3 mr-1" />
                              ROI: {feature.roi}
                            </span>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-center py-8 text-white/60">
                        <p>No time sink features! 🎉</p>
                        <p className="text-sm mt-2">All features have good ROI</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </GlassCard>

            {/* Implementation Timeline */}
            <GlassCard variant="subtle" className="p-8">
              <h2 className="text-2xl font-bold text-white mb-6 flex items-center">
                <Clock className="w-6 h-6 mr-3 text-blue-400" />
                Implementation Timeline
              </h2>
              <div className="space-y-4">
                {features
                  .sort((a, b) => {
                    const priorityOrder = { P0: 0, P1: 1, P2: 2, P3: 3 };
                    return priorityOrder[a.priority as keyof typeof priorityOrder] - priorityOrder[b.priority as keyof typeof priorityOrder];
                  })
                  .map((feature, index) => (
                    <div key={feature.id} className="flex items-center gap-4 bg-white/5 rounded-lg p-4 border border-white/10">
                      <div className="text-2xl font-bold text-white/40">#{index + 1}</div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="font-semibold text-white">{feature.name}</h4>
                          <Badge className={getPriorityColor(feature.priority)}>{feature.priority}</Badge>
                          <Badge className={getStatusColor(feature.status)}>{feature.status}</Badge>
                        </div>
                        <p className="text-sm text-white/60">{feature.description}</p>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-semibold text-white">{feature.estimatedTime}</div>
                        <div className="text-xs text-white/60">ROI: {feature.roi}/10</div>
                      </div>
                    </div>
                  ))}
              </div>
            </GlassCard>
          </div>
        </main>
      </div>
    </AnimatedGradientBg>
  );
}
