import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import frappeui from "frappe-ui/vite"
import path from "path"
import fs from "fs"

export default defineConfig({
  server: {
    port: 8081,
    proxy: getProxyOptions(),
    allowedHosts: true,
  },
  plugins: [
    frappeui({ frontendRoute: "/ecommerce-core" }),
    vue(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  build: {
    outDir: "../ecommerce_core/public/frontend",
    emptyOutDir: true,
    target: "es2015",
    commonjsOptions: {
      include: [/tailwind.config.js/, /node_modules/],
    },
    rollupOptions: {
      output: {
        manualChunks: {
          "frappe-ui": ["frappe-ui"],
        },
      },
    },
  },
  optimizeDeps: {
    include: ["frappe-ui > feather-icons", "socket.io-client"],
  },
})

function getProxyOptions() {
  const config = getCommonSiteConfig()
  const webserver_port = config ? config.webserver_port : 8000
  if (!config) {
    console.log("No common_site_config.json found, using default port 8000")
  }
  return {
    "^/(app|login|api|assets|files|private|socket.io)": {
      target: `http://127.0.0.1:${webserver_port}`,
      ws: true,
      router: function (req) {
        const site_name = req.headers.host.split(":")[0]
        return `http://${site_name}:${webserver_port}`
      },
    },
  }
}

function getCommonSiteConfig() {
  let currentDir = path.resolve(".")
  // traverse up till we find frappe-bench with sites directory
  while (currentDir !== "/") {
    if (
      fs.existsSync(path.join(currentDir, "sites")) &&
      fs.existsSync(path.join(currentDir, "apps"))
    ) {
      let configPath = path.join(currentDir, "sites", "common_site_config.json")
      if (fs.existsSync(configPath)) {
        return JSON.parse(fs.readFileSync(configPath))
      }
      return null
    }
    currentDir = path.resolve(currentDir, "..")
  }
  return null
}
