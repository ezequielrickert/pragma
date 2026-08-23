import { resolve } from "path";
import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        lists: resolve(__dirname, "lists.html"),
      },
    },
  },
  server: {
    port: 5174,
    open: true,
  },
});
