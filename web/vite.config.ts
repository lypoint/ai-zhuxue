import { defineConfig, loadEnv } from "vite";
import { fileURLToPath } from "node:url";

export default defineConfig(({ mode }) => {
  const role = mode === "student" ? "student" : "parent";
  const env = loadEnv(mode, process.cwd(), "PARENT_");
  const firebase = role === "parent" && env.PARENT_FIREBASE_CONFIG
    ? JSON.parse(env.PARENT_FIREBASE_CONFIG) : null;
  if (firebase && (!["apiKey", "appId", "projectId", "measurementId"].every(key => typeof firebase[key] === "string" && firebase[key])
      || !/^\d+:\d+:web:[a-z0-9]+$/i.test(firebase.appId) || !/^G-[A-Z0-9]+$/.test(firebase.measurementId)))
    throw new Error("PARENT_FIREBASE_CONFIG must contain a Web app apiKey, appId, projectId and measurementId.");
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
    define: {
      __WEB_ROLE__: JSON.stringify(role),
      __PARENT_FIREBASE_CONFIG__: JSON.stringify(firebase),
    },
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
          fileURLToPath(new URL("../server/app/locales.json", import.meta.url)),
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
