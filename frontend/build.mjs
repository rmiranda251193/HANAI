// Builds each React island as its own fully independent IIFE bundle.
//
// Rollup does not support IIFE/UMD output for a single "code-splitting"
// build with multiple entry points (even with zero shared chunks between
// them) -- so instead of one `vite build` with four inputs, this runs Vite's
// JS API once per island, each producing exactly one <script>-tag-ready
// file in ../static/react/. See docs/REACT_ISLANDS.md.
import { build } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const outDir = fileURLToPath(new URL("../static/react", import.meta.url));

const entries = {
  lab: "./src/lab/main.jsx",
  "lesson-builder": "./src/lesson-builder/main.jsx",
  analytics: "./src/analytics/main.jsx",
  tutor: "./src/tutor/main.jsx",
};

for (const [name, entry] of Object.entries(entries)) {
  await build({
    // Prevent Vite from picking up frontend/vite.config.js (not used by
    // this script) or any other ambient config.
    configFile: false,
    plugins: [react({ jsxRuntime: "classic" })],
    build: {
      outDir,
      emptyOutDir: false,
      minify: true,
      rollupOptions: {
        input: fileURLToPath(new URL(entry, import.meta.url)),
        external: ["react", "react-dom"],
        output: {
          format: "iife",
          entryFileNames: `${name}.js`,
          globals: { react: "React", "react-dom": "ReactDOM" },
        },
      },
    },
    logLevel: "warn",
  });
  // eslint-disable-next-line no-console
  console.log(`built static/react/${name}.js`);
}
