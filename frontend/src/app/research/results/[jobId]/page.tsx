"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";

export default function ResultsPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params.jobId as string;
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);

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

  async function handleExport(format: "pdf" | "json" | "csv") {
    try {
      let url = "";
      let filename = "";
      if (format === "pdf") {
        url = `${process.env.NEXT_PUBLIC_API_BASE}/export/pdf?jobId=${jobId}`;
        filename = `evidentia-report-${jobId}.pdf`;
      } else {
        // For JSON/CSV, generate client-side from report data
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `evidentia-report-${jobId}.json`;
        a.click();
        return;
      }
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    } catch (e) {
      toast.error("Export failed");
    }
  }

  async function handleRefine(type: "recency" | "counterpoints") {
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/refine/${type}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jobId }),
      });
      const data = await r.json();
      if (data.ok) {
        toast.success("Refined report");
        // Refresh report
        const resp = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/report?jobId=${jobId}`);
        setReport(await resp.json());
      } else {
        toast.error("Refine failed");
      }
    } catch (e) {
      toast.error("Refine failed");
    }
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center text-muted-foreground">Loading report...</div>
        </CardContent>
      </Card>
    );
  }

  if (!report) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center text-destructive">Report not found.</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-6">
      {/* Export and Refine Actions */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Report #{jobId}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => handleRefine("recency")}>
                Emphasize Recency
              </Button>
              <Button variant="outline" size="sm" onClick={() => handleRefine("counterpoints")}>
                Add Counterpoints
              </Button>
              <Separator orientation="vertical" className="mx-2 h-6" />
              <Button size="sm" onClick={() => handleExport("pdf")}>
                Export PDF
              </Button>
              <Button size="sm" variant="outline" onClick={() => handleExport("json")}>
                Export JSON
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
      </Card>

      {/* Evidence Matrix */}
      <Card>
        <CardHeader>
          <CardTitle>Evidence Matrix</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            {report.citations.map((c: any, idx: number) => (
              <div key={idx} className="border rounded-lg p-3 space-y-1">
                <div className="font-medium text-sm">{c.claim_span}</div>
                <div className="text-xs text-muted-foreground italic">
                  "{c.quote_span}"
                </div>
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-blue-600 underline"
                >
                  Source
                </a>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Report Body */}
      <Card>
        <CardHeader>
          <CardTitle>Report</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className="prose max-w-none"
            dangerouslySetInnerHTML={{ __html: report.html }}
          />
        </CardContent>
      </Card>

      {/* Sources */}
      <Card>
        <CardHeader>
          <CardTitle>Sources</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc pl-5 space-y-1">
            {report.sources.map((s: any, idx: number) => (
              <li key={idx}>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 underline"
                >
                  {s.title}
                </a>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
