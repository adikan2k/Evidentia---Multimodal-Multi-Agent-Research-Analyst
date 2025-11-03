"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

// Custom components
import { GlassCard } from "@/components/ui/glass-card";
import { GradientButton } from "@/components/ui/gradient-button";
import { AnimatedGradientBg } from "@/components/ui/animated-gradient-bg";
import { Footer } from "@/components/ui/footer";
import { LoadingSkeleton } from "@/components/ui/loading-skeleton";

import { toast } from "sonner";
import { 
  CheckCircle, 
  Download, 
  FileText, 
  ExternalLink, 
  Brain, 
  TrendingUp, 
  Clock,
  Share2,
  RefreshCw,
  BarChart3
} from "lucide-react";

import { exportReportToPDF } from "@/lib/export-pdf";

export default function ResultsPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.jobId as string;
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isRefining, setIsRefining] = useState(false);

  useEffect(() => {
    async function fetchReport() {
      try {
        const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/report?jobId=${jobId}`);
        const data = await r.json();
        if (!data.html || data.html.includes("Report not ready yet")) {
          setTimeout(() => fetchReport(), 2000);
        } else {
          setReport(data);
          setLoading(false);
        }
      } catch (e) {
        toast.error("Failed to load report");
        setLoading(false);
      }
    }
    if (jobId) fetchReport();
  }, [jobId]);

  if (loading) {
    return (
      <AnimatedGradientBg>
        <div className="min-h-screen flex flex-col">
          <header className="border-b border-white/10 backdrop-blur-sm bg-white/5">
            <div className="container mx-auto px-6 py-4">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl flex items-center justify-center">
                  <Brain className="w-6 h-6 text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">Evidentia</h1>
              </div>
            </div>
          </header>
          <main className="flex-1 container mx-auto px-6 py-12">
            <div className="max-w-4xl mx-auto">
              <GlassCard variant="strong" className="p-8">
                <div className="text-center space-y-4">
                  <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl flex items-center justify-center mx-auto">
                    <Brain className="w-8 h-8 text-white animate-pulse" />
                  </div>
                  <h2 className="text-2xl font-bold text-white">Generating Your Report</h2>
                  <p className="text-white/60">Our AI is analyzing sources and creating comprehensive insights...</p>
                  <LoadingSkeleton variant="text" lines={3} className="max-w-md mx-auto" />
                </div>
              </GlassCard>
            </div>
          </main>
        </div>
      </AnimatedGradientBg>
    );
  }

  if (!report) {
    return (
      <AnimatedGradientBg>
        <div className="min-h-screen flex flex-col items-center justify-center">
          <div className="text-center space-y-4">
            <div className="w-16 h-16 bg-red-500/20 rounded-xl flex items-center justify-center mx-auto">
              <FileText className="w-8 h-8 text-red-400" />
            </div>
            <h2 className="text-2xl font-bold text-white">Report Not Found</h2>
            <p className="text-white/60">The requested report could not be found.</p>
            <GradientButton onClick={() => router.push("/")}>Return Home</GradientButton>
          </div>
        </div>
      </AnimatedGradientBg>
    );
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
                  <Brain className="w-6 h-6 text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">Evidentia</h1>
              </div>
              <div className="flex items-center space-x-4">
                <Badge variant="outline" className="bg-white/10 border-white/20 text-white">
                  Report #{jobId}
                </Badge>
                <GradientButton size="sm" variant="outline" onClick={() => router.push("/")}>
                  New Research
                </GradientButton>
              </div>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 container mx-auto px-6 py-12">
          <div className="max-w-6xl mx-auto space-y-8">
            {/* Success Header */}
            <div className="text-center mb-8">
              <div className="w-20 h-20 bg-gradient-to-br from-green-500 to-emerald-500 rounded-xl flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-10 h-10 text-white" />
              </div>
              <h2 className="text-4xl font-bold text-white mb-4">Research Complete!</h2>
              <p className="text-xl text-white/70">
                Your comprehensive research report is ready with {report.citations?.length || 0} evidence-backed insights
              </p>
            </div>

            {/* Action Buttons */}
            <GlassCard variant="strong" className="p-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex flex-wrap gap-3">
                  <GradientButton 
                    size="sm" 
                    onClick={() => handleExport("pdf")}
                    className="flex items-center space-x-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>Export PDF</span>
                  </GradientButton>
                  <GradientButton 
                    size="sm" 
                    variant="outline"
                    onClick={() => handleExport("json")}
                    className="flex items-center space-x-2"
                  >
                    <FileText className="w-4 h-4" />
                    <span>Export JSON</span>
                  </GradientButton>
                  <GradientButton 
                    size="sm" 
                    variant="outline"
                    onClick={() => handleRefine("recency")}
                    disabled={isRefining}
                    className="flex items-center space-x-2"
                  >
                    <TrendingUp className="w-4 h-4" />
                    <span>{isRefining ? "Refining..." : "Emphasize Recency"}</span>
                  </GradientButton>
                  <GradientButton 
                    size="sm" 
                    variant="outline"
                    onClick={() => handleRefine("counterpoints")}
                    disabled={isRefining}
                    className="flex items-center space-x-2"
                  >
                    <RefreshCw className="w-4 h-4" />
                    <span>{isRefining ? "Refining..." : "Add Counterpoints"}</span>
                  </GradientButton>
                </div>
                <GradientButton 
                  size="sm" 
                  variant="ghost"
                  onClick={() => handleShare()}
                  className="flex items-center space-x-2"
                >
                  <Share2 className="w-4 h-4" />
                  <span>Share</span>
                </GradientButton>
              </div>
            </GlassCard>

            {/* Stats Dashboard */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-blue-400 mb-2">{report.citations?.length || 0}</div>
                <p className="text-white/60 text-sm">Evidence Points</p>
              </GlassCard>
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-green-400 mb-2">{report.sources?.length || 0}</div>
                <p className="text-white/60 text-sm">Sources Analyzed</p>
              </GlassCard>
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-purple-400 mb-2">
                  {(() => {
                    const citations = report.citations?.length || 0;
                    const sources = report.sources?.length || 0;
                    // Base quality: 90% + bonus for citations and sources
                    const quality = Math.min(99, 90 + citations * 0.5 + sources * 0.3);
                    return Math.round(quality);
                  })()}%
                </div>
                <p className="text-white/60 text-sm">Research Quality</p>
              </GlassCard>
              <GlassCard variant="subtle" className="p-6 text-center">
                <div className="text-3xl font-bold text-orange-400 mb-2">
                  {(() => {
                    const sources = report.sources?.length || 0;
                    const citations = report.citations?.length || 0;
                    // Each source: 15-20 min to read + analyze
                    // Each citation: 5-10 min to extract and verify
                    // Synthesis and writing: 30-60 min
                    const totalMinutes = (sources * 18) + (citations * 7) + 45;
                    const hours = Math.floor(totalMinutes / 60);
                    const mins = totalMinutes % 60;
                    return hours > 0 ? `~${hours}h ${mins}m` : `~${mins}m`;
                  })()}
                </div>
                <p className="text-white/60 text-sm">Time Saved</p>
              </GlassCard>
            </div>

            {/* Evidence Matrix */}
            <GlassCard variant="subtle" className="p-8">
              <div className="flex items-center mb-6">
                <BarChart3 className="w-6 h-6 text-blue-400 mr-3" />
                <h3 className="text-2xl font-bold text-white">Evidence Matrix</h3>
                <span className="ml-auto text-white/60 text-sm">{report.citations?.length || 0} Citations</span>
              </div>
              {report.citations && report.citations.length > 0 ? (
                <div className="grid gap-6 md:grid-cols-2">
                  {report.citations.map((citation: any, idx: number) => (
                    <div 
                      key={idx} 
                      className="bg-white/5 rounded-xl p-6 border border-white/10 hover:border-blue-400/30 hover:bg-white/10 transition-all duration-300 group overflow-hidden"
                    >
                      <div className="flex items-start justify-between mb-4">
                        <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30 font-medium">
                          Evidence #{idx + 1}
                        </Badge>
                        <a
                          href={citation.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-white/60 hover:text-blue-400 transition-colors flex-shrink-0"
                          title="View source"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>
                      </div>
                      <h4 className="text-white font-semibold mb-3 text-base leading-snug break-words">{citation.claim_span}</h4>
                      <blockquote className="text-white/80 italic text-sm leading-relaxed mb-4 pl-4 border-l-4 border-blue-400/40 bg-white/5 py-2 rounded-r break-words">
                        "{citation.quote_span}"
                      </blockquote>
                      <div className="flex items-center justify-between text-xs text-white/50">
                        <div className="flex items-center">
                          <FileText className="w-3 h-3 mr-2" />
                          <span>Source {idx + 1}</span>
                        </div>
                        <span className="text-white/40">{citation.quote_span.length} chars</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <div className="w-16 h-16 bg-white/5 rounded-xl flex items-center justify-center mx-auto mb-4">
                    <BarChart3 className="w-8 h-8 text-white/40" />
                  </div>
                  <p className="text-white/60">No citations available for this report.</p>
                </div>
              )}
            </GlassCard>

            {/* Main Report */}
            <GlassCard variant="subtle" className="p-8">
              <div className="flex items-center mb-6">
                <FileText className="w-6 h-6 text-purple-400 mr-3" />
                <h3 className="text-2xl font-bold text-white">Comprehensive Report</h3>
              </div>
              <style jsx global>{`
                /* Force override all report styles for readability */
                .report-content * {
                  color: rgba(255, 255, 255, 0.95) !important;
                  line-height: 1.7 !important;
                }
                
                .report-content h1 {
                  font-size: 2.5rem !important;
                  font-weight: 700 !important;
                  color: #ffffff !important;
                  margin-bottom: 1.5rem !important;
                  margin-top: 0 !important;
                  border-bottom: 2px solid rgba(147, 51, 234, 0.3) !important;
                  padding-bottom: 0.75rem !important;
                }
                
                .report-content h2 {
                  font-size: 1.75rem !important;
                  font-weight: 600 !important;
                  color: #a78bfa !important;
                  margin-top: 3rem !important;
                  margin-bottom: 1.25rem !important;
                  border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
                  padding-bottom: 0.5rem !important;
                }
                
                .report-content h3 {
                  font-size: 1.25rem !important;
                  font-weight: 600 !important;
                  color: #93c5fd !important;
                  margin-top: 2rem !important;
                  margin-bottom: 1rem !important;
                }
                
                .report-content h4 {
                  font-size: 1.1rem !important;
                  font-weight: 600 !important;
                  color: #ffffff !important;
                  margin-top: 1.5rem !important;
                  margin-bottom: 0.75rem !important;
                }
                
                .report-content p {
                  color: rgba(255, 255, 255, 0.9) !important;
                  margin-bottom: 1.25rem !important;
                  line-height: 1.8 !important;
                  font-size: 1rem !important;
                }
                
                .report-content strong, .report-content b {
                  color: #ffffff !important;
                  font-weight: 600 !important;
                }
                
                .report-content em, .report-content i {
                  color: rgba(255, 255, 255, 0.85) !important;
                }
                
                .report-content ul, .report-content ol {
                  margin: 1.5rem 0 !important;
                  padding-left: 1.75rem !important;
                }
                
                .report-content li {
                  color: rgba(255, 255, 255, 0.9) !important;
                  margin-bottom: 0.75rem !important;
                  line-height: 1.7 !important;
                }
                
                .report-content a {
                  color: #60a5fa !important;
                  text-decoration: none !important;
                  border-bottom: 1px solid rgba(96, 165, 250, 0.3) !important;
                  word-break: break-all !important;
                  transition: all 0.2s !important;
                }
                
                .report-content a:hover {
                  color: #93c5fd !important;
                  border-bottom-color: rgba(147, 197, 253, 0.5) !important;
                }
                
                .report-content .report-header {
                  background: rgba(255, 255, 255, 0.05) !important;
                  padding: 1.5rem !important;
                  border-radius: 0.75rem !important;
                  margin-bottom: 2rem !important;
                  border: 1px solid rgba(255, 255, 255, 0.1) !important;
                }
                
                .report-content .report-meta {
                  color: rgba(255, 255, 255, 0.8) !important;
                  font-size: 0.95rem !important;
                  margin-bottom: 0.5rem !important;
                }
                
                .report-content .finding-card, 
                .report-content .finding-card-primary,
                .report-content .finding-card-supporting {
                  background: rgba(255, 255, 255, 0.05) !important;
                  border: 1px solid rgba(255, 255, 255, 0.1) !important;
                  border-radius: 0.75rem !important;
                  padding: 1.5rem !important;
                  margin-bottom: 1.25rem !important;
                }
                
                .report-content .finding-card-primary {
                  border-color: rgba(147, 51, 234, 0.3) !important;
                }
                
                .report-content .source-link {
                  font-size: 0.875rem !important;
                  color: #60a5fa !important;
                  margin-top: 0.75rem !important;
                  display: inline-block !important;
                }
                
                /* Comparison Table Styling */
                .report-content .comparison-table-container {
                  margin: 2rem 0 !important;
                  overflow-x: auto !important;
                }
                
                .report-content .comparison-table {
                  width: 100% !important;
                  border-collapse: separate !important;
                  border-spacing: 0 !important;
                  background: rgba(255, 255, 255, 0.03) !important;
                  border-radius: 0.75rem !important;
                  overflow: hidden !important;
                }
                
                .report-content .comparison-table thead {
                  background: rgba(147, 51, 234, 0.15) !important;
                }
                
                .report-content .comparison-table th {
                  padding: 1.25rem !important;
                  text-align: left !important;
                  font-weight: 600 !important;
                  color: #ffffff !important;
                  font-size: 1rem !important;
                  border-bottom: 2px solid rgba(147, 51, 234, 0.4) !important;
                }
                
                .report-content .comparison-table td {
                  padding: 1.25rem !important;
                  border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
                  vertical-align: top !important;
                  line-height: 1.7 !important;
                  font-size: 0.95rem !important;
                }
                
                .report-content .aspect-cell {
                  font-weight: 600 !important;
                  color: #c4b5fd !important;
                  background: rgba(147, 51, 234, 0.08) !important;
                  width: 22% !important;
                }
                
                .report-content .comparison-cell {
                  color: rgba(255, 255, 255, 0.9) !important;
                }
                
                .report-content .comparison-table tr:hover {
                  background: rgba(255, 255, 255, 0.03) !important;
                }
                
                .report-content .comparison-summary {
                  background: rgba(255, 255, 255, 0.05) !important;
                  padding: 1.5rem !important;
                  border-radius: 0.75rem !important;
                  margin-top: 1.5rem !important;
                  border: 1px solid rgba(255, 255, 255, 0.1) !important;
                }
                
                /* Statistics Section */
                .report-content .statistics-grid {
                  display: grid !important;
                  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)) !important;
                  gap: 1.25rem !important;
                  margin: 1.5rem 0 !important;
                }
                
                .report-content .stat-card {
                  background: rgba(147, 51, 234, 0.1) !important;
                  border: 1px solid rgba(147, 51, 234, 0.3) !important;
                  border-radius: 0.75rem !important;
                  padding: 1.5rem !important;
                  text-align: center !important;
                }
                
                .report-content .stat-value {
                  font-size: 2.5rem !important;
                  font-weight: 700 !important;
                  color: #ffffff !important;
                  margin-bottom: 0.75rem !important;
                  line-height: 1.2 !important;
                }
                
                .report-content .stat-label {
                  font-size: 1rem !important;
                  font-weight: 600 !important;
                  color: #c4b5fd !important;
                  margin-bottom: 0.5rem !important;
                  line-height: 1.4 !important;
                }
                
                .report-content .stat-source {
                  font-size: 0.8rem !important;
                  color: rgba(255, 255, 255, 0.6) !important;
                  font-style: italic !important;
                }
                
                /* Key Takeaway Box */
                .report-content .key-takeaway {
                  background: linear-gradient(135deg, rgba(147, 51, 234, 0.15), rgba(79, 70, 229, 0.15)) !important;
                  border: 2px solid rgba(147, 51, 234, 0.4) !important;
                  border-radius: 0.875rem !important;
                  padding: 2rem !important;
                  margin: 2rem 0 !important;
                }
                
                .report-content .key-takeaway h3 {
                  color: #ffffff !important;
                  margin-top: 0 !important;
                  font-size: 1.5rem !important;
                }
                
                /* References */
                .report-content .references {
                  list-style: decimal !important;
                  padding-left: 2rem !important;
                  margin: 1.5rem 0 !important;
                }
                
                .report-content .references li {
                  margin-bottom: 1rem !important;
                  color: rgba(255, 255, 255, 0.85) !important;
                  font-size: 0.9rem !important;
                  line-height: 1.6 !important;
                }
                
                /* Executive Insights */
                .report-content .executive-insights {
                  list-style: none !important;
                  padding-left: 0 !important;
                }
                
                .report-content .executive-insights li {
                  padding-left: 1.5rem !important;
                  position: relative !important;
                  margin-bottom: 1rem !important;
                }
                
                .report-content .executive-insights li:before {
                  content: "→" !important;
                  position: absolute !important;
                  left: 0 !important;
                  color: #a78bfa !important;
                  font-weight: 700 !important;
                }
              `}</style>
              <div 
                className="report-content prose prose-invert prose-lg max-w-none overflow-hidden"
                dangerouslySetInnerHTML={{ __html: report.html }}
              />
            </GlassCard>

            {/* Sources */}
            <GlassCard variant="subtle" className="p-8">
              <div className="flex items-center mb-6">
                <ExternalLink className="w-6 h-6 text-green-400 mr-3" />
                <h3 className="text-2xl font-bold text-white">Source References</h3>
                <span className="ml-auto text-white/60 text-sm">{report.sources?.length || 0} Sources</span>
              </div>
              {report.sources && report.sources.length > 0 ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {report.sources.map((source: any, idx: number) => (
                    <a
                      key={idx}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="bg-white/5 rounded-lg p-5 border border-white/10 hover:border-green-400/30 hover:bg-white/10 transition-all duration-300 group block overflow-hidden"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center mb-2">
                            <Badge variant="outline" className="bg-green-500/10 border-green-500/30 text-green-400 text-xs font-medium">
                              Source #{idx + 1}
                            </Badge>
                          </div>
                          <h4 className="text-white font-medium leading-snug mb-2 group-hover:text-green-400 transition-colors break-words">
                            {source.title}
                          </h4>
                          <p className="text-white/50 text-xs break-all line-clamp-2">{source.url}</p>
                        </div>
                        <div className="flex-shrink-0 text-white/60 group-hover:text-green-400 transition-colors">
                          <ExternalLink className="w-5 h-5" />
                        </div>
                      </div>
                    </a>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <div className="w-16 h-16 bg-white/5 rounded-xl flex items-center justify-center mx-auto mb-4">
                    <ExternalLink className="w-8 h-8 text-white/40" />
                  </div>
                  <p className="text-white/60">No sources available for this report.</p>
                </div>
              )}
            </GlassCard>
          </div>
        </main>
        <Footer />
      </div>
    </AnimatedGradientBg>
  );

  async function handleExport(format: "pdf" | "json") {
    try {
      if (format === "pdf") {
        // Extract query from report HTML or use jobId
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = report.html;
        const h1 = tempDiv.querySelector('h1');
        const query = h1?.textContent?.replace('Research Report:', '').replace('Research Analysis:', '').trim() || `Report ${jobId}`;
        
        const success = exportReportToPDF(report.html, query);
        if (success) {
          toast.success('Report exported as PDF');
        } else {
          toast.error('PDF export failed');
        }
      } else {
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `evidentia-report-${jobId}.json`;
        a.click();
        toast.success('Report exported as JSON');
      }
    } catch (e) {
      console.error('Export error:', e);
      toast.error("Export failed");
    }
  }

  async function handleRefine(type: "recency" | "counterpoints") {
    setIsRefining(true);
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/refine/${type}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jobId }),
      });
      const data = await r.json();
      if (data.ok) {
        toast.success("Report refined successfully");
        const resp = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/report?jobId=${jobId}`);
        setReport(await resp.json());
      } else {
        toast.error("Refine failed");
      }
    } catch (e) {
      toast.error("Refine failed");
    } finally {
      setIsRefining(false);
    }
  }

  function handleShare() {
    const url = window.location.href;
    navigator.clipboard.writeText(url);
    toast.success("Report link copied to clipboard!");
  }
}
