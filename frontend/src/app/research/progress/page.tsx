"use client";
import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";

// Custom components
import { GlassCard } from "@/components/ui/glass-card";
import { ProgressRing } from "@/components/ui/progress-ring";
import { AnimatedGradientBg } from "@/components/ui/animated-gradient-bg";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

import { Brain, FileText, Search, Zap, CheckCircle, Clock, ArrowRight } from "lucide-react";

export default function ProgressPage() {
  const sp = useSearchParams();
  const router = useRouter();
  const jobId = sp.get("jobId") ?? "";
  const [status, setStatus] = useState<{ phase: string; percent: number; msg?: string }>({
    phase: "planning",
    percent: 5,
  });
  const [startTime] = useState<number>(Date.now());
  const [estimatedTime, setEstimatedTime] = useState<string>("3-5 minutes");

  const steps = [
    { id: "initializing", name: "Initializing", icon: Brain, description: "Setting up research pipeline", avgTime: 10 },
    { id: "discovering_sources", name: "Source Discovery", icon: Search, description: "Searching multiple data sources", avgTime: 30 },
    { id: "ingesting_content", name: "Content Ingestion", icon: FileText, description: "Extracting content from sources", avgTime: 60 },
    { id: "processing_text", name: "Text Processing", icon: FileText, description: "Processing and cleaning extracted text", avgTime: 25 },
    { id: "analyzing_semantics", name: "Semantic Analysis", icon: Brain, description: "Generating embeddings and vectors", avgTime: 40 },
    { id: "ranking_content", name: "Content Ranking", icon: Zap, description: "Ranking sources by relevance", avgTime: 20 },
    { id: "generating_report", name: "Report Generation", icon: CheckCircle, description: "Creating comprehensive research report", avgTime: 35 },
    { id: "completed", name: "Complete", icon: CheckCircle, description: "Ready to view", avgTime: 0 }
  ];

  const currentStepIndex = steps.findIndex(step => step.id === status.phase);
  const currentStep = steps[currentStepIndex] || steps[0];

  useEffect(() => {
    const t = setInterval(async () => {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/status?jobId=${jobId}`);
      const s = await r.json();
      setStatus(s);
      
      // Calculate realistic time estimate
      const currentStepIdx = steps.findIndex(step => step.id === s.phase);
      if (currentStepIdx >= 0) {
        // Sum remaining time for incomplete steps
        let remainingTime = 0;
        for (let i = currentStepIdx; i < steps.length; i++) {
          remainingTime += steps[i].avgTime || 0;
        }
        
        // Adjust based on current progress within step
        const stepProgress = (s.percent - (currentStepIdx * 12.5)) / 12.5;
        const currentStepRemaining = steps[currentStepIdx].avgTime * (1 - stepProgress);
        remainingTime = remainingTime - steps[currentStepIdx].avgTime + currentStepRemaining;
        
        // Format time estimate
        const minutes = Math.ceil(remainingTime / 60);
        const seconds = Math.ceil(remainingTime % 60);
        
        if (minutes > 0) {
          setEstimatedTime(`~${minutes}m ${seconds}s`);
        } else {
          setEstimatedTime(`~${seconds}s`);
        }
      }
      
      if (s.phase === "done") router.push(`/research/report/${jobId}`);
    }, 1200);
    return () => clearInterval(t);
  }, [jobId, router, steps]);

  return (
    <AnimatedGradientBg>
      <div className="min-h-screen flex flex-col">
        {/* Header */}
        <header className="border-b border-white/10 backdrop-blur-sm bg-white/5">
          <div className="container mx-auto px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl flex items-center justify-center">
                  <Brain className="w-6 h-6 text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">Evidentia</h1>
              </div>
              <div className="flex items-center space-x-4">
                <Badge variant="outline" className="bg-white/10 border-white/20 text-white">
                  Job #{jobId}
                </Badge>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 container mx-auto px-6 py-12">
          <div className="max-w-4xl mx-auto">
            {/* Progress Overview */}
            <div className="text-center mb-12">
              <h2 className="text-4xl font-bold text-white mb-4">
                Research in Progress
              </h2>
              <p className="text-xl text-white/70">
                Our AI is analyzing sources and generating your comprehensive report
              </p>
            </div>

            {/* Main Progress Card */}
            <GlassCard variant="strong" className="p-8 mb-8">
              <div className="flex flex-col md:flex-row items-center gap-8">
                {/* Progress Ring */}
                <div className="flex-shrink-0">
                  <ProgressRing 
                    progress={status.percent} 
                    size={160}
                    strokeWidth={12}
                    className="mb-4"
                  />
                </div>

                {/* Current Step Info */}
                <div className="flex-1 text-center md:text-left">
                  <div className="flex items-center justify-center md:justify-start mb-4">
                    <currentStep.icon className="w-8 h-8 text-blue-400 mr-3" />
                    <div>
                      <h3 className="text-2xl font-bold text-white">{currentStep.name}</h3>
                      <p className="text-white/60">{currentStep.description}</p>
                    </div>
                  </div>
                  
                  <div className="bg-white/5 rounded-lg p-4 mb-4">
                    <p className="text-white font-medium">
                      {status.msg || "Processing..."}
                    </p>
                  </div>

                  <div className="flex items-center justify-center md:justify-start text-white/60 text-sm">
                    <Clock className="w-4 h-4 mr-2" />
                    <span>Estimated time remaining: {estimatedTime}</span>
                  </div>
                </div>
              </div>
            </GlassCard>

            {/* Step Timeline */}
            <GlassCard variant="subtle" className="p-8 relative overflow-hidden">
              {/* Animated background particles */}
              <div className="absolute inset-0 overflow-hidden pointer-events-none">
                {[...Array(20)].map((_, i) => (
                  <div
                    key={i}
                    className="absolute w-1 h-1 bg-blue-400/30 rounded-full animate-float"
                    style={{
                      left: `${Math.random() * 100}%`,
                      top: `${Math.random() * 100}%`,
                      animationDelay: `${Math.random() * 3}s`,
                      animationDuration: `${3 + Math.random() * 4}s`
                    }}
                  />
                ))}
              </div>
              
              <h3 className="text-xl font-semibold text-white mb-6 relative z-10">Research Pipeline</h3>
              <div className="space-y-4 relative z-10">
                {steps.map((step, index) => {
                  const isActive = step.id === status.phase;
                  const isCompleted = index < currentStepIndex;
                  const Icon = step.icon;
                  
                  return (
                    <div key={step.id} className="relative">
                      {/* Connecting line with animation */}
                      {index < steps.length - 1 && (
                        <div className="absolute left-6 top-12 w-0.5 h-8 bg-white/10">
                          {isCompleted && (
                            <div className="w-full h-full bg-gradient-to-b from-green-400 to-blue-400 animate-pulse" />
                          )}
                          {isActive && (
                            <div className="w-full bg-gradient-to-b from-blue-400 to-transparent animate-slide-down" />
                          )}
                        </div>
                      )}
                      
                      <div className={`flex items-center space-x-4 transition-all duration-500 ${
                        isActive ? 'scale-105 translate-x-2' : ''
                      }`}>
                        {/* Icon container with glow effect */}
                        <div className="relative">
                          <div className={`flex-shrink-0 w-12 h-12 rounded-full flex items-center justify-center transition-all duration-500 relative z-10 ${
                            isCompleted ? "bg-green-500/20 text-green-400 border-2 border-green-500/50 shadow-lg shadow-green-500/50" :
                            isActive ? "bg-blue-500/20 text-blue-400 border-2 border-blue-500/50 shadow-lg shadow-blue-500/50 animate-pulse-glow" :
                            "bg-white/5 text-white/40 border border-white/20"
                          }`}>
                            <Icon className={`w-6 h-6 transition-all duration-300 ${
                              isActive ? 'animate-bounce-subtle' : ''
                            }`} />
                          </div>
                          
                          {/* Ripple effect for active step */}
                          {isActive && (
                            <>
                              <div className="absolute inset-0 rounded-full bg-blue-400/20 animate-ping" />
                              <div className="absolute inset-0 rounded-full bg-blue-400/10 animate-pulse" style={{ animationDelay: '0.5s' }} />
                            </>
                          )}
                          
                          {/* Success burst for completed */}
                          {isCompleted && (
                            <div className="absolute inset-0 rounded-full bg-green-400/5 animate-pulse" />
                          )}
                        </div>
                        
                        {/* Text content with slide animation */}
                        <div className={`flex-1 transition-all duration-500 ${
                          isActive ? 'translate-x-1' : ''
                        }`}>
                          <h4 className={`font-semibold transition-all duration-500 text-lg ${
                            isCompleted ? "text-green-400" :
                            isActive ? "text-blue-400 animate-pulse-text" :
                            "text-white/40"
                          }`}>
                            {step.name}
                          </h4>
                          <p className={`text-sm transition-all duration-300 ${
                            isActive ? "text-white/80" : "text-white/50"
                          }`}>
                            {step.description}
                          </p>
                        </div>
                        
                        {/* Status indicator with animations */}
                        <div className="flex-shrink-0 relative">
                          {isCompleted && (
                            <CheckCircle className="w-6 h-6 text-green-400 animate-scale-in" />
                          )}
                          {isActive && (
                            <div className="relative">
                              <div className="w-6 h-6 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                              <div className="absolute inset-0 w-6 h-6 border-2 border-blue-300/30 rounded-full animate-ping" />
                            </div>
                          )}
                          {!isActive && !isCompleted && (
                            <Clock className="w-5 h-5 text-white/30" />
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              
              {/* Progress wave effect */}
              <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-blue-400/50 to-transparent animate-wave" />
            </GlassCard>

            {/* Loading Animation */}
            <div className="mt-8 text-center">
              <div className="inline-flex items-center space-x-2 text-white/60">
                <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                <span className="ml-2">Analyzing sources...</span>
              </div>
            </div>
          </div>
        </main>
      </div>
    </AnimatedGradientBg>
  );
}
