import type { ClipperApi, LogItem, ProgressData } from "@/types/api"

/**
 * Obtém a instância da API nativa exposta pelo PyWebView.
 * Aguarda o evento 'pywebviewready' caso ainda não tenha sido injetada.
 */
export async function getClipperApi(): Promise<ClipperApi> {
    if (typeof window !== "undefined" && window.pywebview?.api) {
        return window.pywebview.api
    }

    return new Promise((resolve) => {
        const handler = () => {
            window.removeEventListener("pywebviewready", handler)
            if (window.pywebview?.api) {
                resolve(window.pywebview.api)
            }
        }
        window.addEventListener("pywebviewready", handler)

        // Timeout de segurança para evitar espera infinita se aberto diretamente no navegador
        setTimeout(() => {
            if (window.pywebview?.api) {
                resolve(window.pywebview.api)
            } else {
                console.warn(
                    "PyWebView API não detectada (executando fora do desktop PyWebView).",
                )
            }
        }, 2000)
    })
}

/**
 * Registra listeners para eventos emitidos em tempo real pelo backend Python.
 */
export function subscribeToClipperEvents(callbacks: {
    onProgress?: (data: ProgressData) => void
    onLog?: (data: LogItem) => void
    onClipDone?: (data: Record<string, unknown>) => void
    onPipelineFinished?: (data: {
        success: boolean
        result?: unknown
        error?: string
    }) => void
}): () => void {
    // Inicializa a ponte global caso ainda não exista
    if (!window.__clipperBridge) {
        window.__clipperBridge = {
            listeners: {},
            on(event, callback) {
                if (!this.listeners[event]) this.listeners[event] = []
                this.listeners[event].push(callback as (data: unknown) => void)
            },
            emit(event, data) {
                if (this.listeners[event]) {
                    this.listeners[event].forEach((fn) => fn(data))
                }
            },
        }
    }

    const { onProgress, onLog, onClipDone, onPipelineFinished } = callbacks

    if (onProgress)
        window.__clipperBridge.on("progress", (data) =>
            onProgress(data as ProgressData),
        )
    if (onLog)
        window.__clipperBridge.on("log", (data) => onLog(data as LogItem))
    if (onClipDone)
        window.__clipperBridge.on("clip_done", (data) =>
            onClipDone(data as Record<string, unknown>),
        )
    if (onPipelineFinished) {
        window.__clipperBridge.on("pipeline_finished", (data) =>
            onPipelineFinished(
                data as { success: boolean; result?: unknown; error?: string },
            ),
        )
    }

    return () => {
        // Unsubscribe cleanup se necessário
    }
}
