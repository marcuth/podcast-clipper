import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import {
    getClipperApi,
    getClipperBridge,
    subscribeToClipperEvents,
} from "@/lib/bridge"
import type { LogItem, PipelineOptions, ProgressData } from "@/types/api"

export { getClipperApi, getClipperBridge }

const INITIAL_PROGRESS: ProgressData = {
    step: "idle",
    step_index: 0,
    percentage: 0,
    message: "Pronto para iniciar.",
    current_clip: 0,
    total_clips: 0,
    data: {},
}

export function useClipperStatus() {
    const [isRunning, setIsRunning] = useState<boolean>(false)
    const [progress, setProgress] = useState<ProgressData>(INITIAL_PROGRESS)
    const [logs, setLogs] = useState<LogItem[]>([])

    const syncStatus = useCallback(async () => {
        try {
            const api = await getClipperApi()
            const status = await api.get_status()
            setIsRunning(status.is_running)
            if (status.progress) {
                setProgress(status.progress)
            }
            if (status.logs && status.logs.length > 0) {
                setLogs(status.logs)
            }
        } catch (error) {
            console.error("Erro ao sincronizar status com o backend:", error)
        }
    }, [])

    useEffect(() => {
        syncStatus()

        const unsubscribe = subscribeToClipperEvents({
            onProgress: (newProgress) => {
                setProgress(newProgress)
                if (newProgress.step === "done") {
                    setIsRunning(false)
                }
            },
            onLog: (newLog) => {
                setLogs((previousLogs) => {
                    const updatedLogs = [...previousLogs, newLog]
                    return updatedLogs.length > 500
                        ? updatedLogs.slice(-500)
                        : updatedLogs
                })
            },
            onClipDone: (clipData) => {
                toast.success(
                    `Corte finalizado: ${clipData.name || "Novo clipe"}!`,
                )
            },
            onPipelineFinished: (result) => {
                setIsRunning(false)
                if (result.success) {
                    toast.success("Processamento concluído com sucesso!")
                } else if (result.error) {
                    toast.error(`Falha no processo: ${result.error}`)
                }
            },
        })

        const intervalId = setInterval(() => {
            if (isRunning) {
                syncStatus()
            }
        }, 1500)

        return () => {
            unsubscribe()
            clearInterval(intervalId)
        }
    }, [isRunning, syncStatus])

    const startPipeline = useCallback(async (options: PipelineOptions) => {
        try {
            const api = await getClipperApi()
            setIsRunning(true)
            setProgress({
                ...INITIAL_PROGRESS,
                step: "init",
                message: "Iniciando pipeline...",
            })

            const response = await api.start_pipeline(options)
            if (!response.success) {
                setIsRunning(false)
                toast.error(
                    response.error || "Não foi possível iniciar o pipeline.",
                )
                return false
            }

            toast.info(
                "Processo iniciado! Acompanhe o progresso em tempo real.",
            )
            return true
        } catch (error) {
            setIsRunning(false)
            toast.error(`Erro ao disparar pipeline: ${String(error)}`)
            return false
        }
    }, [])

    const cancelPipeline = useCallback(async () => {
        try {
            const api = await getClipperApi()
            const response = await api.cancel_pipeline()
            if (response.success) {
                toast.warning("Sinal de cancelamento enviado.")
            }
            return response.success
        } catch (error) {
            toast.error(`Erro ao cancelar pipeline: ${String(error)}`)
            return false
        }
    }, [])

    const clearLogs = useCallback(() => {
        setLogs([])
    }, [])

    return {
        isRunning,
        progress,
        logs,
        startPipeline,
        cancelPipeline,
        clearLogs,
        refreshStatus: syncStatus,
    }
}
