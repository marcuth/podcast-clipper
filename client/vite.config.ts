import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(import.meta.dirname, "./src"),
        },
    },
    server: {
        port: 5173,
        proxy: {
            "/media": {
                target: "http://127.0.0.1:48123",
                changeOrigin: true,
            },
        },
    },
    build: {
        outDir: "../src/gui/web",
        emptyOutDir: true,
    },
})
