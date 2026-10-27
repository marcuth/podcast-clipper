import {
    Check,
    Copy,
    ListDashes,
    Stop,
    Terminal,
    Trash,
} from "@phosphor-icons/react"
import { cn } from "cn"
import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { LogItem, ProgressData } from "@/types/api"

interface PipelineMonitorProps {
    isRunning: boolean
    progress: ProgressData
    logs: LogItem[]
    onCancel: () => void
    onClearLogs: () => void
    className?: string
}

const PHASES = [
    { key: "metadata", label: "Metadados" },
    { key: "heatmap", label: "Heatmap" },
    { key: "download", label: "Preparação" },
    { key: "transcribe", label: "Transcrição" },
    { key: "heuristics", label: "Seleção IA" },
    { key: "cutting", label: "Renderização" },
]

export function PipelineMonitor({
    isRunning,
    progress,
    logs,
    onCancel,
    onClearLogs,
    className,
}: PipelineMonitorProps) {
    const [filterLevel, setFilterLevel] = useState<string>("all")
    const [autoScroll, setAutoScroll] = useState<boolean>(true)
    const scrollAreaRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (autoScroll && scrollAreaRef.current) {
            const viewport = scrollAreaRef.current.querySelector(
                "[data-slot='scroll-area-viewport']",
            ) as HTMLElement | null
            if (viewport) {
                viewport.scrollTop = viewport.scrollHeight
            }
        }
    }, [logs, autoScroll])

    const filteredLogs = logs.filter((log) => {
        if (filterLevel === "all") return true
        return log.level === filterLevel
    })

    const copyLogs = () => {
        const text = logs
            .map((item) => `[${item.level.toUpperCase()}] ${item.message}`)
            .join("\n")
        navigator.clipboard.writeText(text)
        toast.success("Logs copiados para a área de transferência!")
    }

    const currentStepIndex = progress.step_index || 0

    return (
        <Card
            className={cn(
                "border-border/60 bg-card/70 shadow-lg backdrop-blur-md",
                className,
            )}
        >
            <CardHeader className="flex flex-row items-center justify-between pb-3">
                <div>
                    <CardTitle className="flex items-center gap-2 text-base font-semibold">
                        <Terminal
                            size={18}
                            className="text-primary-ink"
                            weight="bold"
                        />
                        <span>Monitoramento do Pipeline</span>
                    </CardTitle>
                    <CardDescription className="text-xs">
                        Acompanhe o processamento de áudio, visão computacional
                        e IA
                    </CardDescription>
                </div>

                <div className="flex items-center gap-2">
                    {isRunning && (
                        <Button
                            variant="destructive"
                            size="sm"
                            onClick={onCancel}
                            className="h-8 gap-1 text-xs font-semibold"
                        >
                            <Stop size={14} weight="bold" />
                            <span>Cancelar</span>
                        </Button>
                    )}
                </div>
            </CardHeader>

            <CardContent className="space-y-6">
                <div className="relative">
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-6">
                        {PHASES.map((phase, index) => {
                            const phaseNumber = index + 1
                            const isCompleted =
                                currentStepIndex > phaseNumber ||
                                progress.step === "done"
                            const isCurrent =
                                currentStepIndex === phaseNumber && isRunning

                            let statusBadge = (
                                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[11px] font-bold text-muted-foreground">
                                    {phaseNumber}
                                </span>
                            )

                            if (isCompleted) {
                                statusBadge = (
                                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
                                        <Check size={12} weight="bold" />
                                    </span>
                                )
                            } else if (isCurrent) {
                                statusBadge = (
                                    <span className="relative flex h-5 w-5 items-center justify-center">
                                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75"></span>
                                        <span className="relative flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-white">
                                            {phaseNumber}
                                        </span>
                                    </span>
                                )
                            }

                            return (
                                <div
                                    key={phase.key}
                                    className={`flex items-center gap-2 rounded-lg border p-2 transition-all ${
                                        isCurrent
                                            ? "border-primary/60 bg-primary/10 shadow-xs"
                                            : isCompleted
                                              ? "border-emerald-500/30 bg-emerald-500/5 text-foreground/90"
                                              : "border-border/40 bg-muted/20 text-muted-foreground"
                                    }`}
                                >
                                    {statusBadge}
                                    <span className="truncate text-xs font-medium">
                                        {phase.label}
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                </div>

                <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-foreground">
                            {progress.message || "Aguardando início..."}
                        </span>
                        <span className="font-mono font-semibold text-primary-ink">
                            {progress.percentage.toFixed(0)}%
                        </span>
                    </div>
                    <Progress value={progress.percentage} className="h-2.5" />
                    {progress.total_clips > 0 && (
                        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                            <span>
                                Processando corte {progress.current_clip} de{" "}
                                {progress.total_clips}
                            </span>
                            <span>
                                {(
                                    (progress.current_clip /
                                        progress.total_clips) *
                                    100
                                ).toFixed(0)}
                                % dos clipes
                            </span>
                        </div>
                    )}
                </div>

                <div className="overflow-hidden rounded-lg border border-border/60 bg-black/70 shadow-inner">
                    <div className="flex items-center justify-between border-b border-border/40 bg-muted/40 px-3 py-1.5 text-xs">
                        <div className="flex items-center gap-2 font-mono text-muted-foreground">
                            <Terminal size={14} />
                            <span>
                                Terminal de Execução ({filteredLogs.length})
                            </span>
                        </div>

                        <div className="flex items-center gap-1.5">
                            <select
                                value={filterLevel}
                                onChange={(e) => setFilterLevel(e.target.value)}
                                className="h-6 rounded border border-border/40 bg-background px-1.5 text-[11px] text-foreground focus:outline-none"
                            >
                                <option value="all">Todos</option>
                                <option value="info">Info</option>
                                <option value="warning">Avisos</option>
                                <option value="error">Erros</option>
                            </select>

                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setAutoScroll(!autoScroll)}
                                className={`h-6 w-6 text-xs ${autoScroll ? "text-primary-ink" : "text-muted-foreground"}`}
                                title={
                                    autoScroll
                                        ? "Auto-scroll ativado"
                                        : "Auto-scroll pausado"
                                }
                            >
                                <ListDashes size={13} />
                            </Button>

                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={copyLogs}
                                className="h-6 w-6 text-muted-foreground hover:text-foreground"
                                title="Copiar logs"
                            >
                                <Copy size={13} />
                            </Button>

                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={onClearLogs}
                                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                                title="Limpar terminal"
                            >
                                <Trash size={13} />
                            </Button>
                        </div>
                    </div>

                    <div ref={scrollAreaRef} className="h-48 w-full">
                        <ScrollArea className="h-full w-full p-3 font-mono text-[11px] leading-relaxed">
                            {filteredLogs.length === 0 ? (
                                <div className="flex h-36 items-center justify-center text-xs text-muted-foreground/60">
                                    Nenhum log emitido ainda.
                                </div>
                            ) : (
                                <div className="space-y-1">
                                    {filteredLogs.map((log, index) => {
                                        let levelColor = "text-muted-foreground"
                                        if (log.level === "warning")
                                            levelColor =
                                                "text-amber-400 font-semibold"
                                        if (log.level === "error")
                                            levelColor =
                                                "text-red-400 font-bold"

                                        return (
                                            <div
                                                key={index}
                                                className="flex items-start gap-2 break-all"
                                            >
                                                <span className="shrink-0 select-none text-muted-foreground/40">
                                                    {String(index + 1).padStart(
                                                        3,
                                                        "0",
                                                    )}
                                                </span>
                                                <span
                                                    className={`shrink-0 uppercase text-[10px] ${levelColor}`}
                                                >
                                                    [{log.level}]
                                                </span>
                                                <span
                                                    className={`flex-1 ${levelColor}`}
                                                >
                                                    {log.message}
                                                </span>
                                            </div>
                                        )
                                    })}
                                </div>
                            )}
                        </ScrollArea>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
