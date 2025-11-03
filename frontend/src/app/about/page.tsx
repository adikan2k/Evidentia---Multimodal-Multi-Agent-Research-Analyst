"use client";

import { GlassCard } from "@/components/ui/glass-card";
import { AnimatedGradientBg } from "@/components/ui/animated-gradient-bg";
import { GradientButton } from "@/components/ui/gradient-button";
import { Badge } from "@/components/ui/badge";
import { Footer } from "@/components/ui/footer";
import { 
  Brain, 
  Search, 
  FileText, 
  Zap, 
  Globe, 
  BookOpen, 
  Video, 
  GraduationCap,
  Shield,
  Rocket,
  Users,
  TrendingUp
} from "lucide-react";
import Link from "next/link";

export default function AboutPage() {
  return (
    <AnimatedGradientBg>
      <div className="min-h-screen">
        {/* Header */}
        <header className="border-b border-white/10 backdrop-blur-sm bg-white/5">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <Link href="/" className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg flex items-center justify-center">
                  <Brain className="w-5 h-5 text-white" />
                </div>
                <span className="text-xl font-bold text-white">Evidentia</span>
              </Link>
              <Link href="/">
                <GradientButton variant="outline" size="sm">
                  Back to Home
                </GradientButton>
              </Link>
            </div>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          {/* Hero Section */}
          <div className="text-center mb-16">
            <h1 className="text-5xl font-bold text-white mb-6 bg-gradient-to-r from-blue-400 to-purple-400 bg-clip-text text-transparent">
              About Evidentia
            </h1>
            <p className="text-xl text-white/80 max-w-3xl mx-auto">
              Your AI-powered research assistant that transforms complex queries into comprehensive, 
              evidence-based reports in seconds.
            </p>
          </div>

          {/* Mission */}
          <GlassCard className="p-8 mb-12">
            <div className="flex items-center mb-6">
              <Rocket className="w-8 h-8 text-blue-400 mr-4" />
              <h2 className="text-3xl font-bold text-white">Our Mission</h2>
            </div>
            <p className="text-white/80 text-lg leading-relaxed">
              Evidentia democratizes research by making advanced AI-powered analysis accessible to everyone. 
              We bridge the gap between information overload and actionable insights, helping researchers, 
              students, professionals, and curious minds discover knowledge efficiently and effectively.
            </p>
          </GlassCard>

          {/* Features Grid */}
          <div className="mb-12">
            <h2 className="text-3xl font-bold text-white text-center mb-8">Core Capabilities</h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
              <GlassCard variant="subtle" className="p-6">
                <Search className="w-8 h-8 text-blue-400 mb-4" />
                <h3 className="text-xl font-semibold text-white mb-3">Multi-Source Search</h3>
                <p className="text-white/70">
                  Searches across DuckDuckGo, Wikipedia, YouTube, and academic databases to find the most relevant sources.
                </p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6">
                <Brain className="w-8 h-8 text-purple-400 mb-4" />
                <h3 className="text-xl font-semibold text-white mb-3">Semantic Analysis</h3>
                <p className="text-white/70">
                  Advanced AI processes and understands content context, extracting meaningful insights and patterns.
                </p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6">
                <FileText className="w-8 h-8 text-green-400 mb-4" />
                <h3 className="text-xl font-semibold text-white mb-3">Professional Reports</h3>
                <p className="text-white/70">
                  Generates structured, academic-quality reports with proper citations and evidence matrices.
                </p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6">
                <Video className="w-8 h-8 text-red-400 mb-4" />
                <h3 className="text-xl font-semibold text-white mb-3">Multimodal Content</h3>
                <p className="text-white/70">
                  Processes text, video transcripts, academic papers, and various document formats.
                </p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6">
                <TrendingUp className="w-8 h-8 text-orange-400 mb-4" />
                <h3 className="text-xl font-semibold text-white mb-3">Real-time Progress</h3>
                <p className="text-white/70">
                  Watch your research progress through each phase with detailed status updates.
                </p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6">
                <Shield className="w-8 h-8 text-cyan-400 mb-4" />
                <h3 className="text-xl font-semibold text-white mb-3">Source Verification</h3>
                <p className="text-white/70">
                  Every claim is backed by verifiable sources with complete citation tracking.
                </p>
              </GlassCard>
            </div>
          </div>

          
          {/* Use Cases */}
          <div className="mb-12">
            <h2 className="text-3xl font-bold text-white text-center mb-8">Who Uses Evidentia?</h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
              <GlassCard variant="subtle" className="p-6 text-center">
                <Users className="w-12 h-12 text-blue-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-white mb-2">Students</h3>
                <p className="text-white/70 text-sm">Research papers and study materials</p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6 text-center">
                <BookOpen className="w-12 h-12 text-green-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-white mb-2">Researchers</h3>
                <p className="text-white/70 text-sm">Literature reviews and analysis</p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6 text-center">
                <Globe className="w-12 h-12 text-purple-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-white mb-2">Professionals</h3>
                <p className="text-white/70 text-sm">Industry insights and trends</p>
              </GlassCard>

              <GlassCard variant="subtle" className="p-6 text-center">
                <Zap className="w-12 h-12 text-orange-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-white mb-2">Curious Minds</h3>
                <p className="text-white/70 text-sm">Lifelong learning and discovery</p>
              </GlassCard>
            </div>
          </div>

          {/* Creators */}
          <GlassCard className="p-8 text-center">
            <h2 className="text-3xl font-bold text-white mb-6">Meet the Creators</h2>
            <div className="max-w-3xl mx-auto">
              <p className="text-white/80 text-lg mb-8">
                Evidentia was developed by <strong className="text-white">Aditya Kanbargi</strong> and <strong className="text-white">Sanjana Kadambe Muralidhar</strong> 
                as part of their commitment to advancing research technology and making knowledge discovery accessible to everyone.
              </p>
              <div className="grid md:grid-cols-2 gap-6 mb-8">
                <div className="bg-white/5 p-6 rounded-lg border border-white/10">
                  <h3 className="text-xl font-semibold text-white mb-3">Aditya Kanbargi</h3>
                  <p className="text-white/70 text-sm">Full-stack developer & AI integration specialist</p>
                </div>
                <div className="bg-white/5 p-6 rounded-lg border border-white/10">
                  <h3 className="text-xl font-semibold text-white mb-3">Sanjana Kadambe Muralidhar</h3>
                  <p className="text-white/70 text-sm">Data scientist & machine learning researcher</p>
                </div>
              </div>
              <p className="text-white/60 italic">
                "AI-powered research, simplified for everyone."
              </p>
            </div>
          </GlassCard>

          {/* CTA */}
          <GlassCard className="p-8 text-center">
            <h2 className="text-3xl font-bold text-white mb-4">Ready to Transform Your Research?</h2>
            <p className="text-white/80 mb-6 max-w-2xl mx-auto">
              Join thousands of researchers who are already using Evidentia to accelerate their discovery process.
            </p>
            <Link href="/">
              <GradientButton size="lg" className="text-lg px-8 py-3">
                Start Researching Now
              </GradientButton>
            </Link>
          </GlassCard>
        </main>
        <Footer />
      </div>
    </AnimatedGradientBg>
  );
}
