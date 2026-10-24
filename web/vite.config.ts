import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

export default defineConfig(({ mode }) => {
  const role = mode === "student" ? "student" : "parent";
  return {
    plugins: [
      {
        name: "role-home-screen",
        transformIndexHtml: () => [
          {
            tag: "link",
            attrs: { rel: "manifest", href: `/${role}.webmanifest` },
            injectTo: "head",
          },
          {
            tag: "link",
            attrs: { rel: "icon", type: "image/svg+xml", href: "/icon.svg" },
            injectTo: "head",
          },
          {
            tag: "link",
            attrs: { rel: "apple-touch-icon", href: "/apple-touch-icon.png" },
            injectTo: "head",
          },
        ],
      },
    ],
    define: { __WEB_ROLE__: JSON.stringify(role) },
    build: {
      outDir: `dist/${role}`,
      target: ["es2020", "safari15"],
      sourcemap: false,
    },
    server: {
      fs: {
        allow: [
          fileURLToPath(new URL(".", import.meta.url)),
          fileURLToPath(new URL("../app/app_core/assets", import.meta.url)),
        ],
      },
      proxy: {
        "/api": {
          target: process.env.WEB_DEV_API || "http://127.0.0.1:8100",
          rewrite: (p) => p.replace(/^\/api/, ""),
        },
      },
    },
  };
});
