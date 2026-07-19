import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The backend's CORS allowlist expects the UI on localhost:3000.
// strictPort: if 3000 is taken (an old dev server still running), fail
// loudly instead of silently moving to 3001 where CORS blocks the API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 3000, strictPort: true },
});
