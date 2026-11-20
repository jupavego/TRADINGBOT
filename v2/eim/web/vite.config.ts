// Servidor de desarrollo de la mesa (puerto 5173). La web habla con la API a través del mismo
// origen: `/v2` (HTTP y WebSocket) se reenvía a la API local del puerto 8000. Así funciona también
// en el navegador integrado de Claude, que bloquea las peticiones de una página a otro puerto
// (ERR_BLOCKED_BY_CLIENT, visto el 2026-11-20). La API sigue escuchando solo en 127.0.0.1.
import { defineConfig } from 'vite'

const api = { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true }

export default defineConfig({
  server: { proxy: { '/v2': api } },
  preview: { proxy: { '/v2': api } },
})
