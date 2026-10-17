import {
    ChartBar,
    Clock,
    Cloud,
    Crop,
    FilmStrip,
    Flame,
    Lightning,
    MagnifyingGlass,
    Play,
    Sparkle,
    TextT,
    Users,
} from "@phosphor-icons/react"
import { useState } from "react"
import { toast } from "sonner"

import { PipelineMonitor } from "@/components/pipeline-monitor"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { VideoPreviewCard } from "@/components/video-preview-card"
import { getClipperApi } from "@/lib/bridge"
import type {
    ClippingStrategy,
    LogItem,
    PipelineOptions,
    ProgressData,
    TranscriptionMode,
    VideoInfo,
} from "@/types/api"

interface ShortsStudioTabProps {
    isRunning?: boolean
    isPipelineRunning?: boolean
    progress?: ProgressData
    logs?: LogItem[]
    onStartPipeline?: (options: PipelineOptions) => Promise<boolean>
    onCancelPipeline?: () => void
    onClearLogs?: () => void
}

const getSliderValue = (
    sliderValueInput: number | readonly number[],
): number =>
    Array.isArray(sliderValueInput)
        ? sliderValueInput[0]
        : (sliderValueInput as number)

export function ShortsStudioTab({
    isRunning,
    isPipelineRunning,
    progress,
    logs,
    onStartPipeline,
    onCancelPipeline,
    onClearLogs,
}: ShortsStudioTabProps) {
    const activeIsRunning = isRunning ?? isPipelineRunning ?? false
    const [videoUrl, setVideoUrl] = useState<string>("")
    const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null)
    const [isLoadingInfo, setIsLoadingInfo] = useState<boolean>(false)

    const [clippingStrategy, setClippingStrategy] =
        useState<ClippingStrategy>("ai")
    const [transcriptionMode, setTranscriptionMode] =
        useState<TranscriptionMode>("yt_partial")
    const [useHeatmap, setUseHeatmap] = useState<boolean>(true)
    const [renderSubtitles, setRenderSubtitles] = useState<boolean>(true)
    const [useWhisperSubtitles, setUseWhisperSubtitles] =
        useState<boolean>(true)
    const [enableSplitScreen, setEnableSplitScreen] = useState<boolean>(true)
    const [splitScreenChance, _setSplitScreenChance] = useState<number>(0.5)
    const [applyVignette, setApplyVignette] = useState<boolean>(true)
    const [vignetteAngle, _setVignetteAngle] = useState<string>("PI/4")
    const [onlyTimestamps, setOnlyTimestamps] = useState<boolean>(false)
    const [maxClips, setMaxClips] = useState<number>(8)

    const handlePaste = async () => {
        try {
            const text = await navigator.clipboard.readText()
            if (text) {
                setVideoUrl(text.trim())
                fetchVideoInfo(text.trim())
            }
        } catch {
            toast.error("Não foi possível ler a área de transferência.")
        }
    }

    const fetchVideoInfo = async (urlToFetch?: string) => {
        const targetUrl = (urlToFetch || videoUrl).trim()
        if (!targetUrl) {
            toast.error("Insira uma URL do YouTube para buscar.")
            return
        }

        setIsLoadingInfo(true)
        try {
            const api = await getClipperApi()
            const response = await api.get_video_info(targetUrl)
            if (response.success && response.data) {
                setVideoInfo(response.data)
                toast.success("Vídeo encontrado com sucesso!")
            } else {
                toast.error(
                    response.error || "Não foi possível carregar o vídeo.",
                )
            }
        } catch (error) {
            toast.error(`Erro ao buscar vídeo: ${String(error)}`)
        } finally {
            setIsLoadingInfo(false)
        }
    }

    const handleStart = async () => {
        if (!videoUrl.trim()) {
            toast.error("Por favor, informe a URL do YouTube.")
            return
        }

        const options: PipelineOptions = {
            url: videoUrl.trim(),
            clipping_strategy: clippingStrategy,
            transcription_mode: transcriptionMode,
            use_heatmap: useHeatmap,
            render_subtitles: renderSubtitles,
            use_whisper_subtitles: useWhisperSubtitles,
            enable_split_screen: enableSplitScreen,
            split_screen_chance: splitScreenChance,
            apply_vignette: applyVignette,
            vignette_angle: vignetteAngle,
            only_timestamps: onlyTimestamps,
            is_long_clip: false,
            max_clips: maxClips,
        }

        if (onStartPipeline) {
            await onStartPipeline(options)
        } else {
            const api = await getClipperApi()
            const res = await api.start_pipeline(options)
            if (res.success) {
                toast.success("Processamento de shorts iniciado com sucesso!")
            } else {
                toast.error(res.error || "Erro ao iniciar pipeline.")
            }
        }
    }

    return (
        <div className="space-y-6">
            <Card className="border-border/60 bg-card/60 shadow-md backdrop-blur-sm">
                <CardHeader className="pb-3">
                    <CardTitle className="text-base font-semibold">
                        Link do Episódio / Podcast
                    </CardTitle>
                    <CardDescription className="text-xs">
                        Insira a URL de qualquer vídeo público do YouTube para
                        iniciar o corte automático
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex flex-col gap-2 sm:flex-row">
                        <Input
                            placeholder="https://www.youtube.com/watch?v=... ou https://youtu.be/..."
                            value={videoUrl}
                            onChange={(e) => setVideoUrl(e.target.value)}
                            onKeyDown={(e) =>
                                e.key === "Enter" && fetchVideoInfo()
                            }
                            className="flex-1 bg-background/80"
                        />
                        <div className="flex gap-2">
                            <Button
                                variant="outline"
                                onClick={handlePaste}
                                className="text-xs"
                                title="Colar da área de transferência"
                            >
                                Colar
                            </Button>
                            <Button
                                onClick={() => fetchVideoInfo()}
                                disabled={isLoadingInfo || !videoUrl.trim()}
                                className="gap-1.5 text-xs font-semibold"
                            >
                                <MagnifyingGlass size={15} weight="bold" />
                                <span>Buscar</span>
                            </Button>
                        </div>
                    </div>

                    <VideoPreviewCard
                        videoInfo={videoInfo}
                        isLoading={isLoadingInfo}
                        onClear={() => {
                            setVideoInfo(null)
                            setVideoUrl("")
                        }}
                    />
                </CardContent>
            </Card>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <Card className="border-border/60 bg-card/60 shadow-md">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-semibold">
                            Estratégia de Seleção dos Cortes
                        </CardTitle>
                        <CardDescription className="text-xs">
                            Como a aplicação identifica e classifica os momentos
                            virais
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div
                            onClick={() => setClippingStrategy("ai")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                clippingStrategy === "ai"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary">
                                <Sparkle size={18} weight="fill" />
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-foreground">
                                        ✨ IA Gemini (Recomendado)
                                    </span>
                                    <Badge
                                        variant="secondary"
                                        className="text-[10px] text-primary"
                                    >
                                        Mais Inteligente
                                    </Badge>
                                </div>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    Avaliação narrativa profunda com Vercel AI
                                    SDK. Encontra ganchos fortes, discussões
                                    impactantes e raciocínios com começo, meio e
                                    fim.
                                </p>
                            </div>
                        </div>

                        <div
                            onClick={() => setClippingStrategy("heuristics")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                clippingStrategy === "heuristics"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                                <ChartBar size={18} weight="bold" />
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-foreground">
                                        📊 Heurísticas & Estatísticas
                                    </span>
                                </div>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    Método analítico baseado em gatilhos
                                    textuais de curiosidade, perguntas
                                    retóricas, contrastes de fala e picos do
                                    heatmap do YouTube.
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="border-border/60 bg-card/60 shadow-md">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-semibold">
                            Modo de Download & Transcrição
                        </CardTitle>
                        <CardDescription className="text-xs">
                            Equilíbrio entre velocidade, consumo de internet e
                            precisão
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div
                            onClick={() => setTranscriptionMode("assemblyai")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                transcriptionMode === "assemblyai"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sky-500/20 text-sky-400">
                                <Cloud size={18} weight="fill" />
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-foreground">
                                        🚀 AssemblyAI (Cloud API)
                                    </span>
                                    <Badge
                                        variant="outline"
                                        className="border-sky-500/40 text-[10px] text-sky-400"
                                    >
                                        Alta Precisão
                                    </Badge>
                                </div>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    Transcreve na nuvem com AssemblyAI
                                    Universal-3. Carimbos milimétricos por
                                    palavra, pontuação avançada e sem consumir
                                    CPU local.
                                </p>
                            </div>
                        </div>

                        <div
                            onClick={() => setTranscriptionMode("yt_partial")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                transcriptionMode === "yt_partial"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
                                <Lightning size={18} weight="fill" />
                            </div>
                            <div className="flex-1">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-foreground">
                                        ⚡ Legendas YouTube (Parcial)
                                    </span>
                                    <Badge
                                        variant="outline"
                                        className="border-emerald-500/40 text-[10px] text-emerald-400"
                                    >
                                        Ultra Rápido
                                    </Badge>
                                </div>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    Não baixa o vídeo todo. Analisa as legendas
                                    oficiais e faz download somente dos trechos
                                    selecionados (economiza 90% de banda).
                                </p>
                            </div>
                        </div>

                        <div
                            onClick={() => setTranscriptionMode("yt_full")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                transcriptionMode === "yt_full"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                                <FilmStrip size={18} weight="bold" />
                            </div>
                            <div className="flex-1">
                                <span className="text-xs font-bold text-foreground">
                                    ⚖️ Legendas YouTube (Completo)
                                </span>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    Baixa o vídeo inteiro previamente em 720p.
                                    Ideal para conexão estável.
                                </p>
                            </div>
                        </div>

                        <div
                            onClick={() => setTranscriptionMode("whisper")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                transcriptionMode === "whisper"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
                                <Clock size={18} weight="bold" />
                            </div>
                            <div className="flex-1">
                                <span className="text-xs font-bold text-foreground">
                                    🎯 Local Faster-Whisper
                                </span>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    Gera transcrição do zero com IA no áudio.
                                    Essencial para vídeos sem legendas.
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            <Card className="border-border/60 bg-card/60 shadow-md">
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-semibold">
                        Otimizações de Edição & Formato (9:16)
                    </CardTitle>
                    <CardDescription className="text-xs">
                        Recursos visuais automáticos para maximizar a retenção
                        em TikTok, Shorts e Reels
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/20 p-3">
                            <div className="space-y-0.5">
                                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                                    <Flame
                                        size={14}
                                        className="text-orange-500"
                                        weight="fill"
                                    />
                                    <span>Heatmap do YouTube</span>
                                </div>
                                <p className="text-[11px] text-muted-foreground">
                                    Impulsiona trechos com maior pico de
                                    repetição
                                </p>
                            </div>
                            <Switch
                                checked={useHeatmap}
                                onCheckedChange={setUseHeatmap}
                            />
                        </div>

                        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/20 p-3">
                            <div className="space-y-0.5">
                                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                                    <TextT
                                        size={14}
                                        className="text-primary"
                                        weight="bold"
                                    />
                                    <span>Legendas Dinâmicas</span>
                                </div>
                                <p className="text-[11px] text-muted-foreground">
                                    Grava legendas animadas diretamente no vídeo
                                </p>
                            </div>
                            <Switch
                                checked={renderSubtitles}
                                onCheckedChange={setRenderSubtitles}
                            />
                        </div>

                        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/20 p-3">
                            <div className="space-y-0.5">
                                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                                    <Sparkle
                                        size={14}
                                        className="text-yellow-400"
                                        weight="fill"
                                    />
                                    <span>Whisper nas Legendas</span>
                                </div>
                                <p className="text-[11px] text-muted-foreground">
                                    Sincronização milimétrica das palavras
                                </p>
                            </div>
                            <Switch
                                checked={useWhisperSubtitles && renderSubtitles}
                                onCheckedChange={setUseWhisperSubtitles}
                                disabled={!renderSubtitles}
                            />
                        </div>

                        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/20 p-3">
                            <div className="space-y-0.5">
                                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                                    <Users
                                        size={14}
                                        className="text-cyan-400"
                                        weight="bold"
                                    />
                                    <span>Split-Screen (2 Pessoas)</span>
                                </div>
                                <p className="text-[11px] text-muted-foreground">
                                    Divide a tela em 2 blocos quando houver 2
                                    rostos
                                </p>
                            </div>
                            <Switch
                                checked={enableSplitScreen}
                                onCheckedChange={setEnableSplitScreen}
                            />
                        </div>

                        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/20 p-3">
                            <div className="space-y-0.5">
                                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                                    <Crop
                                        size={14}
                                        className="text-purple-400"
                                        weight="bold"
                                    />
                                    <span>Vinheta Cinematográfica</span>
                                </div>
                                <p className="text-[11px] text-muted-foreground">
                                    Bordas escurecidas para foco no locutor
                                </p>
                            </div>
                            <Switch
                                checked={applyVignette}
                                onCheckedChange={setApplyVignette}
                            />
                        </div>

                        <div className="flex items-center justify-between gap-3 rounded-lg border border-border/40 bg-muted/20 p-3">
                            <div className="space-y-0.5">
                                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                                    <Clock
                                        size={14}
                                        className="text-emerald-400"
                                        weight="bold"
                                    />
                                    <span>Apenas Timestamps</span>
                                </div>
                                <p className="text-[11px] text-muted-foreground">
                                    Gera títulos e horários sem renderizar
                                    vídeos
                                </p>
                            </div>
                            <Switch
                                checked={onlyTimestamps}
                                onCheckedChange={setOnlyTimestamps}
                            />
                        </div>
                    </div>
                </CardContent>
            </Card>

            <Card className="border-border/60 bg-card/60 shadow-md">
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <FilmStrip
                                size={18}
                                className="text-primary"
                                weight="bold"
                            />
                            <div>
                                <CardTitle className="text-sm font-semibold">
                                    Quantidade de Vídeos Curtos a Extrair
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    Defina quantos shorts virais independentes a
                                    IA deve selecionar e renderizar
                                </CardDescription>
                            </div>
                        </div>
                        <Badge
                            variant="outline"
                            className="border-primary/40 bg-primary/10 font-mono text-xs font-bold text-primary px-3 py-1"
                        >
                            {maxClips} {maxClips === 1 ? "short" : "shorts"}
                        </Badge>
                    </div>
                </CardHeader>

                <CardContent className="space-y-4 pt-1">
                    <div className="space-y-3">
                        <div className="flex items-center justify-between text-xs">
                            <Label className="text-muted-foreground font-medium">
                                Arraste o slider para ajustar a quantidade:
                            </Label>
                            <span className="font-mono text-sm font-bold text-primary">
                                {maxClips}{" "}
                                {maxClips === 1
                                    ? "vídeo vertical"
                                    : "vídeos verticais"}
                            </span>
                        </div>

                        <Slider
                            value={[maxClips]}
                            onValueChange={(sliderValue) =>
                                setMaxClips(getSliderValue(sliderValue))
                            }
                            min={1}
                            max={20}
                            step={1}
                            className="py-1"
                        />

                        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                            <span>1 short (mínimo)</span>
                            <div className="flex items-center gap-1.5">
                                {[3, 5, 8, 10, 15].map((presetNumber) => (
                                    <Button
                                        key={presetNumber}
                                        type="button"
                                        variant={
                                            maxClips === presetNumber
                                                ? "secondary"
                                                : "outline"
                                        }
                                        size="sm"
                                        onClick={() =>
                                            setMaxClips(presetNumber)
                                        }
                                        className="h-6 px-2 text-[10px] font-mono"
                                    >
                                        {presetNumber}
                                    </Button>
                                ))}
                            </div>
                            <span>20 shorts (máximo)</span>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <div className="flex flex-col items-center justify-center gap-3 py-2">
                <Button
                    size="lg"
                    onClick={handleStart}
                    disabled={activeIsRunning || !videoUrl.trim()}
                    className="h-12 w-full gap-2 px-8 text-sm font-bold shadow-xl shadow-primary/20 sm:w-auto sm:min-w-64"
                >
                    <Play size={18} weight="fill" />
                    <span>
                        {activeIsRunning
                            ? "Processando Pipeline..."
                            : "Gerar Clipes Verticais com IA"}
                    </span>
                </Button>
            </div>

            {progress &&
                logs &&
                (activeIsRunning ||
                    progress.step !== "idle" ||
                    logs.length > 0) && (
                    <PipelineMonitor
                        isRunning={activeIsRunning}
                        progress={progress}
                        logs={logs}
                        onCancel={onCancelPipeline || (() => {})}
                        onClearLogs={onClearLogs || (() => {})}
                    />
                )}
        </div>
    )
}
