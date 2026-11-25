import { ImageResponse } from "next/og";

// The picture shown when a link to the site is shared: the desk, a sheet, and three marks.
// It carries no numbers, so it cannot go out of date.
export const alt = "Evidentia: do the citations say what the answer says?";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const INK = "#141413";
const ROWS = [
  { colour: "#17603c", name: "Supported", path: "M4.5 12.5l5 5L19.5 6.5" },
  { colour: "#a12b22", name: "Not on the cited page", path: "M6 6l12 12M18 6L6 18" },
  { colour: "#27527c", name: "Needs a human", path: "M8.5 9a3.5 3.5 0 1 1 5.4 2.9c-1.2.8-1.9 1.5-1.9 3.1M12 18.6v.4" },
];

export default function Image() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: "#edece7",
        color: INK,
        padding: "64px 72px",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column" }}>
        <div style={{ fontSize: 30, fontWeight: 600 }}>Evidentia</div>
        <div style={{ marginTop: 28, fontSize: 76, fontWeight: 700, lineHeight: 1.02, letterSpacing: -3, maxWidth: 980 }}>
          Do the citations say what the answer says?
        </div>
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          background: "#ffffff",
          border: "1px solid #d3d1c8",
          borderRadius: 4,
          padding: "30px 40px",
        }}
      >
        {ROWS.map((row) => (
          <div key={row.name} style={{ display: "flex", alignItems: "center" }}>
            <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke={row.colour} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
              <path d={row.path} />
            </svg>
            <div style={{ marginLeft: 12, fontSize: 30, fontWeight: 600, color: row.colour }}>{row.name}</div>
          </div>
        ))}
      </div>
    </div>,
    size,
  );
}
