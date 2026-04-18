import { ImageResponse } from "next/og";

export const runtime = "edge";

export function GET() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#09090b",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "30px",
        }}
      >
        <div
          style={{
            color: "#60a5fa",
            fontSize: 110,
            fontFamily: "serif",
            lineHeight: 1,
            marginTop: 8,
          }}
        >
          ⚖
        </div>
      </div>
    ),
    { width: 192, height: 192 }
  );
}
