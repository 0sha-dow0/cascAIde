/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin when the UI is hosted separately (e.g. UI on Butterbase, API on Render). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
