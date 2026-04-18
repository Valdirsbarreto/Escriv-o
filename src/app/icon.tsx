import { ImageResponse } from "next/og";

export const size = { width: 512, height: 512 };
export const contentType = "image/png";

export default function Icon() {
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
          borderRadius: "80px",
        }}
      >
        <div
          style={{
            color: "#60a5fa",
            fontSize: 300,
            fontFamily: "serif",
            lineHeight: 1,
            marginTop: 20,
          }}
        >
          ⚖
        </div>
      </div>
    ),
    { ...size }
  );
}
