import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "HireStack AI — AI-Powered Career Intelligence Platform";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "sans-serif",
          padding: "60px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            marginBottom: "32px",
          }}
        >
          <div
            style={{
              width: "64px",
              height: "64px",
              borderRadius: "16px",
              background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginRight: "20px",
              fontSize: "32px",
              color: "white",
              fontWeight: 700,
            }}
          >
            H
          </div>
          <span
            style={{
              fontSize: "42px",
              fontWeight: 700,
              color: "white",
              letterSpacing: "-0.02em",
            }}
          >
            HireStack AI
          </span>
        </div>
        <div
          style={{
            fontSize: "28px",
            color: "#94a3b8",
            textAlign: "center",
            lineHeight: 1.5,
            maxWidth: "800px",
          }}
        >
          Stop Applying. Start Landing.
        </div>
        <div
          style={{
            fontSize: "18px",
            color: "#64748b",
            textAlign: "center",
            marginTop: "20px",
            maxWidth: "700px",
          }}
        >
          6 AI agents build your perfect application package in under 3 minutes
        </div>
      </div>
    ),
    { ...size }
  );
}
