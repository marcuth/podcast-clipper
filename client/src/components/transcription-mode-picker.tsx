import { Clock, Cloud, FilmStrip, Lightning } from "@phosphor-icons/react"
import type { ComponentType } from "react"

import { Badge } from "@/components/ui/badge"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import type { TranscriptionMode } from "@/types/api"

interface ModeOption {
    value: TranscriptionMode
    title: string
    description: string
    icon: ComponentType<{ size?: number; weight?: "fill" | "bold" }>
    iconClassName: string
    badge?: { label: string; className: string }
}

const MODE_OPTIONS: ModeOption[] = [
    {
        value: "assemblyai",
        title: "AssemblyAI (Cloud API)",
        description:
            "Transcreve na nuvem com carimbos milimétricos por palavra, sem usar a CPU local.",
        icon: Cloud,
        iconClassName: "bg-sky-500/20 text-sky-400",
        badge: {
            label: "Alta Precisão",
            className: "border-sky-500/40 text-sky-400",
        },
    },
    {
        value: "yt_full",
        title: "Legendas YouTube (Completo)",
        description:
            "Baixa o vídeo inteiro em 720p e usa as legendas oficiais. Ideal para conexão estável.",
        icon: FilmStrip,
        iconClassName: "bg-emerald-500/20 text-emerald-400",
        badge: {
            label: "Padrão",
            className: "border-emerald-500/40 text-emerald-400",
        },
    },
    {
        value: "yt_partial",
        title: "Legendas YouTube (Parcial)",
        description:
            "Baixa só os trechos selecionados. Muito lento, mas consome bem menos banda.",
        icon: Lightning,
        iconClassName: "bg-muted text-foreground",
        badge: {
            label: "Muito Lento",
            className: "border-amber-500/40 text-amber-400",
        },
    },
    {
        value: "whisper",
        title: "Local Faster-Whisper",
        description:
            "Gera a transcrição do zero no áudio. Essencial para vídeos sem legendas.",
        icon: Clock,
        iconClassName: "bg-indigo-500/20 text-indigo-400",
    },
]

interface TranscriptionModePickerProps {
    value: TranscriptionMode
    onChange: (mode: TranscriptionMode) => void
    layout?: "stacked" | "grid"
    className?: string
}

export function TranscriptionModePicker({
    value,
    onChange,
    layout = "stacked",
    className,
}: TranscriptionModePickerProps) {
    return (
        <Card
            className={`border-border/60 bg-card/60 shadow-md ${className ?? ""}`}
        >
            <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">
                    Modo de Download & Transcrição
                </CardTitle>
                <CardDescription className="text-xs">
                    Equilíbrio entre velocidade, consumo de internet e precisão
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div
                    role="radiogroup"
                    aria-label="Modo de download e transcrição"
                    className={`grid gap-2 ${layout === "grid" ? "md:grid-cols-2" : "grid-cols-1"}`}
                >
                    {MODE_OPTIONS.map((option) => {
                        const Icon = option.icon
                        const selected = value === option.value

                        return (
                            <button
                                key={option.value}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                onClick={() => onChange(option.value)}
                                className={`flex items-start gap-3 rounded-lg border p-3 text-left transition-all outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                                    selected
                                        ? "border-primary bg-primary/10 shadow-xs"
                                        : "border-border/40 bg-muted/20 hover:border-border"
                                }`}
                            >
                                <div
                                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${option.iconClassName}`}
                                >
                                    <Icon size={18} weight="fill" />
                                </div>
                                <div className="flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <span className="text-xs font-bold text-foreground">
                                            {option.title}
                                        </span>
                                        {option.badge && (
                                            <Badge
                                                variant="outline"
                                                className={`text-[10px] ${option.badge.className}`}
                                            >
                                                {option.badge.label}
                                            </Badge>
                                        )}
                                    </div>
                                    <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                        {option.description}
                                    </p>
                                </div>
                            </button>
                        )
                    })}
                </div>
            </CardContent>
        </Card>
    )
}
