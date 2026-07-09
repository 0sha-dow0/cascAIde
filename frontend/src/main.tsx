import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "@fontsource-variable/outfit";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";
import Root from "./Root";
import { ThemeProvider } from "@/components/theme-provider";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <ThemeProvider>
        <Root />
      </ThemeProvider>
    </StrictMode>,
  );
}
