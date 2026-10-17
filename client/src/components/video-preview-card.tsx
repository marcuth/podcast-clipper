import { Clock, Eye, Trash, User, YoutubeLogo } from "@phosphor-icons/react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { VideoInfo } from "@/types/api"

interface VideoPreviewCardProps {
    videoInfo: VideoInfo | null
    isLoading: boolean
    onClear: () => void
}

function formatDuration(seconds: number): string {
    const totalSeconds = Math.floor(seconds)
    const hours = Math.floor(totalSeconds / 3600)
    const minutes = Math.floor((totalSeconds % 3600) / 60)
    const remainingSeconds = totalSeconds % 60

    if (hours > 0) {
        return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`
    }
    return `${minutes.toString().padStart(2, "0")}:${remainingSeconds.toString().padStart(2, "0")}`
}

function formatViews(views: number): string {
    if (views >= 1_000_000) {
        return `${(views / 1_000_000).toFixed(1)}M`
    }
    if (views >= 1_000) {
        return `${(views / 1_000).toFixed(0)}k`
    }
    return views.toLocaleString("pt-BR")
}

export function VideoPreviewCard({
    videoInfo,
    isLoading,
    onClear,
}: VideoPreviewCardProps) {
    if (isLoading) {
        return (
            <Card className="border-border/50 bg-muted/20">
                <CardContent className="flex flex-col gap-4 p-4 sm:flex-row">
                    <Skeleton className="h-32 w-full rounded-lg sm:w-56" />
                    <div className="flex flex-1 flex-col justify-between space-y-2">
                        <div className="space-y-2">
                            <Skeleton className="h-5 w-3/4" />
                            <Skeleton className="h-4 w-1/2" />
                        </div>
                        <div className="flex gap-2">
                            <Skeleton className="h-4 w-20" />
                            <Skeleton className="h-4 w-24" />
                        </div>
                    </div>
                </CardContent>
            </Card>
        )
    }

    if (!videoInfo) {
        return null
    }

    return (
        <Card className="overflow-hidden border-border/60 bg-card/60 shadow-md backdrop-blur-sm transition-all hover:border-primary/40">
            <CardContent className="flex flex-col gap-4 p-4 sm:flex-row">
                <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black sm:w-56 sm:shrink-0">
                    <img
                        src={videoInfo.thumbnail}
                        alt={videoInfo.title}
                        className="h-full w-full object-cover"
                    />
                    <div className="absolute right-2 bottom-2 flex items-center gap-1 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-semibold text-white backdrop-blur-xs">
                        <Clock size={12} weight="bold" />
                        <span>{formatDuration(videoInfo.duration)}</span>
                    </div>
                </div>

                <div className="flex flex-1 flex-col justify-between">
                    <div>
                        <div className="flex items-start justify-between gap-2">
                            <h3 className="line-clamp-2 text-sm font-semibold tracking-tight text-foreground sm:text-base">
                                {videoInfo.title}
                            </h3>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={onClear}
                                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                                title="Limpar vídeo"
                            >
                                <Trash size={16} />
                            </Button>
                        </div>

                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1 font-medium text-foreground/80">
                                <User size={13} weight="bold" />
                                <span>
                                    {videoInfo.author || "Canal YouTube"}
                                </span>
                            </div>
                            {videoInfo.views > 0 && (
                                <>
                                    <span>•</span>
                                    <div className="flex items-center gap-1">
                                        <Eye size={13} />
                                        <span>
                                            {formatViews(videoInfo.views)} views
                                        </span>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    <div className="mt-3 flex items-center gap-2">
                        <Badge
                            variant="secondary"
                            className="flex items-center gap-1 text-[11px] text-red-500"
                        >
                            <YoutubeLogo size={14} weight="fill" />
                            <span>Validado</span>
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                            Pronto para processamento
                        </span>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
