import type { ClipperApi, LogItem, ProgressData } from "@/types/api"

/**
 * Obtém a instância da API nativa exposta pelo PyWebView.
 * Aguarda o evento 'pywebviewready' caso ainda não tenha sido injetada.
 */
export function getClipperBridge(): ClipperApi | null {
    if (typeof window !== "undefined" && window.pywebview?.api) {
        return window.pywebview.api
    }
    return null
}

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
    if (typeof window !== "undefined") {
        if (!window.__clipperBridge) {
            window.__clipperBridge = {
                listeners: {},
                on(event: string, callback: (data: unknown) => void) {
                    if (!this.listeners[event]) this.listeners[event] = []
                    this.listeners[event].push(callback)
                },
                off(event: string, callback: (data: unknown) => void) {
                    if (!this.listeners[event]) return
                    this.listeners[event] = this.listeners[event].filter(
                        (fn) => fn !== callback,
                    )
                },
                emit(event: string, data: unknown) {
                    if (this.listeners[event]) {
                        this.listeners[event].forEach((fn) => fn(data))
                    }
                },
            }
        }
    }

    const { onProgress, onLog, onClipDone, onPipelineFinished } = callbacks

    const progressHandler = onProgress
        ? (data: unknown) => onProgress(data as ProgressData)
        : null
    const logHandler = onLog
        ? (data: unknown) => onLog(data as LogItem)
        : null
    const clipDoneHandler = onClipDone
        ? (data: unknown) => onClipDone(data as Record<string, unknown>)
        : null
    const finishedHandler = onPipelineFinished
        ? (data: unknown) =>
              onPipelineFinished(
                  data as {
                      success: boolean
                      result?: unknown
                      error?: string
                  },
              )
        : null

    if (window.__clipperBridge) {
        if (progressHandler)
            window.__clipperBridge.on("progress", progressHandler)
        if (logHandler) window.__clipperBridge.on("log", logHandler)
        if (clipDoneHandler)
            window.__clipperBridge.on("clip_done", clipDoneHandler)
        if (finishedHandler)
            window.__clipperBridge.on("pipeline_finished", finishedHandler)
    }

    return () => {
        if (window.__clipperBridge) {
            if (progressHandler)
                window.__clipperBridge.off("progress", progressHandler)
            if (logHandler) window.__clipperBridge.off("log", logHandler)
            if (clipDoneHandler)
                window.__clipperBridge.off("clip_done", clipDoneHandler)
            if (finishedHandler)
                window.__clipperBridge.off("pipeline_finished", finishedHandler)
        }
    }
}
