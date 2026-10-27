import { CaretUp, TerminalWindow } from "@phosphor-icons/react"
import { useState } from "react"

import { PipelineMonitor } from "@/components/pipeline-monitor"
import { Button } from "@/components/ui/button"
import {
    Drawer,
    DrawerContent,
    DrawerTitle,
    DrawerTrigger,
} from "@/components/ui/drawer"
import type { LogItem, ProgressData } from "@/types/api"

interface PipelineMonitorDrawerProps {
    isRunning: boolean
    progress: ProgressData
    logs: LogItem[]
    onCancel: () => void
    onClearLogs: () => void
}

export function PipelineMonitorDrawer({
    isRunning,
    progress,
    logs,
    onCancel,
    onClearLogs,
}: PipelineMonitorDrawerProps) {
    const [isOpen, setIsOpen] = useState<boolean>(isRunning)
    const [wasRunning, setWasRunning] = useState<boolean>(isRunning)

    if (isRunning !== wasRunning) {
        setWasRunning(isRunning)
        if (isRunning) {
            setIsOpen(true)
        }
    }

    if (!isRunning && logs.length === 0) {
        return null
    }

    return (
        <Drawer
            open={isOpen}
            onOpenChange={setIsOpen}
            modal={false}
            showSwipeHandle
        >
            {!isOpen && (
                <DrawerTrigger
                    render={
                        <Button
                            variant="outline"
                            className="fixed bottom-4 left-1/2 z-40 h-10 max-w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 gap-2 rounded-full border-border/60 bg-card/90 px-4 text-xs shadow-xl backdrop-blur-md"
                        />
                    }
                >
                    {isRunning ? (
                        <span className="relative flex h-2 w-2 shrink-0">
                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
                            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
                        </span>
                    ) : (
                        <TerminalWindow
                            size={14}
                            className="shrink-0 text-primary-ink"
                        />
                    )}
                    <span className="truncate font-medium">
                        {isRunning
                            ? progress.message
                            : "Monitor de Execução do Pipeline"}
                    </span>
                    {isRunning && (
                        <span className="shrink-0 font-mono font-semibold text-primary-ink">
                            {progress.percentage.toFixed(0)}%
                        </span>
                    )}
                    <CaretUp size={12} className="shrink-0" />
                </DrawerTrigger>
            )}

            <DrawerContent>
                <DrawerTitle className="sr-only">
                    Monitoramento do Pipeline
                </DrawerTitle>
                <div className="mx-auto w-full max-w-7xl overflow-y-auto px-4 pb-4 sm:px-6 lg:px-8">
                    <PipelineMonitor
                        isRunning={isRunning}
                        progress={progress}
                        logs={logs}
                        onCancel={onCancel}
                        onClearLogs={onClearLogs}
                        className="border-none bg-transparent shadow-none backdrop-blur-none"
                    />
                </div>
            </DrawerContent>
        </Drawer>
    )
}
