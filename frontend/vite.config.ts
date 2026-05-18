import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
    plugins: [react()],

    // This placeholder will be replaced at container runtime
    base: '/__URLPATH__/',

    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },

    server: {
        port: 5173,
        open: true,
    },

    define: {
        'import.meta.env.VITE_URL_PREFIX': JSON.stringify('__URLPATH__'),
    },
})