import { CheckCircle, Sparkle, WarningCircle } from "@phosphor-icons/react"

import { Badge } from "@/components/ui/badge"
import type { ProgressData } from "@/types/api"

interface HeaderProps {
    isRunning: boolean
    progress?: ProgressData
    currentStep?: string
    activeModel?: string
    geminiModel?: string
    pageTitle?: string
}

export function Header({
    isRunning,
    progress,
    currentStep,
    activeModel,
    geminiModel,
    pageTitle,
}: HeaderProps) {
    const displayedModel = activeModel || geminiModel

    const renderStatusBadge = () => {
        if (isRunning) {
            return (
                <Badge
                    variant="outline"
                    className="flex items-center gap-1.5 border-primary/40 bg-primary/10 px-3 py-1 text-xs font-medium text-primary shadow-sm"
                >
                    <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75"></span>
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-primary"></span>
                    </span>
                    <span>
                        {progress
                            ? `Executando (${progress.percentage.toFixed(0)}%)`
                            : currentStep || "Executando..."}
                    </span>
                </Badge>
            )
        }

        if (progress?.step === "error") {
            return (
                <Badge
                    variant="destructive"
                    className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium shadow-sm"
                >
                    <WarningCircle size={14} weight="bold" />
                    <span>Erro no Processo</span>
                </Badge>
            )
        }

        if (progress?.step === "done") {
            return (
                <Badge
                    variant="outline"
                    className="flex items-center gap-1.5 border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400 shadow-sm"
                >
                    <CheckCircle size={14} weight="fill" />
                    <span>Finalizado</span>
                </Badge>
            )
        }

        return (
            <Badge
                variant="outline"
                className="flex items-center gap-1.5 border-muted-foreground/30 bg-muted/40 px-3 py-1 text-xs font-medium text-muted-foreground"
            >
                <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
                <span>Pronto</span>
            </Badge>
        )
    }

    return (
        <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-md">
            <div className="flex h-16 w-full items-center justify-between px-6">
                <div className="flex items-center gap-3">
                    {pageTitle ? (
                        <div className="flex items-center gap-2">
                            <h2 className="text-base font-bold text-foreground">
                                {pageTitle}
                            </h2>
                        </div>
                    ) : (
                        <div className="flex items-center gap-2">
                            <span className="bg-gradient-to-r from-foreground via-foreground to-foreground/70 bg-clip-text text-base font-bold tracking-tight text-transparent">
                                Podcast Clipper
                            </span>
                            <Badge
                                variant="secondary"
                                className="h-5 px-1.5 text-[10px] font-semibold text-primary"
                            >
                                AI v2.5
                            </Badge>
                        </div>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    {displayedModel && (
                        <div className="hidden items-center gap-1.5 rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1 text-xs font-medium text-muted-foreground sm:flex">
                            <Sparkle
                                size={13}
                                className="text-primary"
                                weight="fill"
                            />
                            <span>{displayedModel}</span>
                        </div>
                    )}

                    {renderStatusBadge()}
                </div>
            </div>
        </header>
    )
}
