import { AuditPicker } from "@/components/AuditPicker";
import { RecordBand } from "@/components/RecordBand";

// The home page is the auditor (D-045). The research agent lives at /research. The auditor's own
// record is rendered here, on the server, so the eval data never ships to the browser (D-053).
export default function Page() {
  return <AuditPicker band={<RecordBand />} />;
}
