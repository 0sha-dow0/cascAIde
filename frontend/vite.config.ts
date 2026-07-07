import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API = "http://127.0.0.1:8099";
const proxy = Object.fromEntries(
  ["/repos", "/incidents", "/transplants", "/health"].map((p) => [
    p,
    { target: API, changeOrigin: true },
  ]),
);

export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5173, proxy },
  build: { outDir: "dist", emptyOutDir: true },
});
