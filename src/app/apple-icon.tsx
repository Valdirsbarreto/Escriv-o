import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
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
          borderRadius: "36px",
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
    { ...size }
  );
}
