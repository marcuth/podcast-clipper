import {
    Clock,
    FloppyDisk,
    FolderOpen,
    Image,
    MagnifyingGlass,
    Play,
    Sparkle,
    SpeakerSlash,
} from "@phosphor-icons/react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { PipelineMonitor } from "@/components/pipeline-monitor"
import { TranscriptionModePicker } from "@/components/transcription-mode-picker"
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
    LogItem,
    PipelineOptions,
    ProgressData,
    TranscriptionMode,
    VideoInfo,
} from "@/types/api"

interface LongClipsTabProps {
    isRunning?: boolean
    isPipelineRunning?: boolean
    progress?: ProgressData
    logs?: LogItem[]
    onStartPipeline?: (options: PipelineOptions) => Promise<boolean>
    onCancelPipeline?: () => void
    onClearLogs?: () => void
}

function parseTimeToSeconds(timeStr: string): number | null {
    if (!timeStr || !timeStr.trim()) return null
    const parts = timeStr.trim().split(":").map(Number)
    if (parts.some(isNaN)) return null

    if (parts.length === 3) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    }
    if (parts.length === 2) {
        return parts[0] * 60 + parts[1]
    }
    if (parts.length === 1) {
        return parts[0]
    }
    return null
}

const getSliderValue = (val: number | readonly number[]): number =>
    Array.isArray(val) ? val[0] : (val as number)

export function LongClipsTab({
    isRunning,
    isPipelineRunning,
    progress,
    logs,
    onStartPipeline,
    onCancelPipeline,
    onClearLogs,
}: LongClipsTabProps) {
    const activeIsRunning = isRunning ?? isPipelineRunning ?? false
    const [videoUrl, setVideoUrl] = useState<string>("")
    const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null)
    const [isLoadingInfo, setIsLoadingInfo] = useState<boolean>(false)

    const [selectionMode, setSelectionMode] = useState<"ai" | "custom">("ai")
    const [customStart, setCustomStart] = useState<string>("")
    const [customEnd, setCustomEnd] = useState<string>("")

    const [transcriptionMode, setTranscriptionMode] =
        useState<TranscriptionMode>("yt_full")

    const [minDurationMinutes, setMinDurationMinutes] = useState<number>(3)
    const [maxDurationMinutes, setMaxDurationMinutes] = useState<number>(15)
    const [maxClips, setMaxClips] = useState<number>(3)

    const [removeSilence, setRemoveSilence] = useState<boolean>(true)
    const [silenceThresholdDb, setSilenceThresholdDb] = useState<number>(-30)
    const [minSilenceDuration, setMinSilenceDuration] = useState<number>(0.6)
    const [silencePadding, setSilencePadding] = useState<number>(0.15)

    const [enableOverlay, setEnableOverlay] = useState<boolean>(() => {
        if (typeof window !== "undefined") {
            const savedState = localStorage.getItem(
                "podcast_clipper_enable_overlay",
            )
            const savedPath = localStorage.getItem(
                "podcast_clipper_overlay_path",
            )
            if (savedState !== null) return savedState === "true"
            return Boolean(savedPath && savedPath.trim())
        }
        return false
    })
    const [overlayPath, setOverlayPath] = useState<string>(() => {
        if (typeof window !== "undefined") {
            return localStorage.getItem("podcast_clipper_overlay_path") || ""
        }
        return ""
    })
    const [defaultSavedOverlay, setDefaultSavedOverlay] = useState<string>("")
    const [isSavingOverlayDefault, setIsSavingOverlayDefault] =
        useState<boolean>(false)

    const updateOverlayPath = (newPath: string) => {
        setOverlayPath(newPath)
        if (typeof window !== "undefined") {
            localStorage.setItem("podcast_clipper_overlay_path", newPath)
            if (newPath.trim()) {
                setEnableOverlay(true)
                localStorage.setItem("podcast_clipper_enable_overlay", "true")
            }
        }
    }

    const updateEnableOverlay = (enabled: boolean) => {
        setEnableOverlay(enabled)
        if (typeof window !== "undefined") {
            localStorage.setItem(
                "podcast_clipper_enable_overlay",
                String(enabled),
            )
        }
    }

    useEffect(() => {
        let isMounted = true
        async function loadDefaultOverlaySettings() {
            try {
                const api = await getClipperApi()
                const systemInfo = await api.get_system_info()
                if (isMounted && systemInfo) {
                    if (systemInfo.default_long_clip_overlay) {
                        setDefaultSavedOverlay(
                            systemInfo.default_long_clip_overlay,
                        )
                        const currentLocal = localStorage.getItem(
                            "podcast_clipper_overlay_path",
                        )
                        if (!currentLocal) {
                            setOverlayPath(systemInfo.default_long_clip_overlay)
                            setEnableOverlay(true)
                        }
                    }
                }
            } catch (error) {
                console.error("Erro ao carregar overlay padrão:", error)
            }
        }
        loadDefaultOverlaySettings()
        return () => {
            isMounted = false
        }
    }, [])

    const handleSelectOverlay = async () => {
        try {
            const api = await getClipperApi()
            const result = await api.select_overlay_file()
            if (result.success && result.file_path) {
                updateOverlayPath(result.file_path)
                updateEnableOverlay(true)
                toast.success("Arquivo de overlay selecionado com sucesso!")
            } else if (result.error) {
                toast.error(result.error)
            }
        } catch (error) {
            toast.error(`Erro ao abrir seletor de arquivos: ${String(error)}`)
        }
    }

    const handleSaveDefaultOverlay = async () => {
        if (!overlayPath.trim()) {
            toast.error(
                "Informe um caminho de overlay para salvar como padrão.",
            )
            return
        }
        setIsSavingOverlayDefault(true)
        try {
            const api = await getClipperApi()
            const response = await api.save_default_long_clip_overlay(
                overlayPath.trim(),
            )
            if (response.success) {
                setDefaultSavedOverlay(overlayPath.trim())
                toast.success("Overlay salvo como padrão no .env com sucesso!")
            } else {
                toast.error(
                    response.error ||
                        "Não foi possível salvar o overlay como padrão.",
                )
            }
        } catch (error) {
            toast.error(`Erro ao salvar overlay padrão: ${String(error)}`)
        } finally {
            setIsSavingOverlayDefault(false)
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

    const applySilencePreset = (preset: "soft" | "balanced" | "aggressive") => {
        if (preset === "soft") {
            setSilenceThresholdDb(-35)
            setMinSilenceDuration(0.8)
            setSilencePadding(0.2)
            toast.info("Preset Suave aplicado: remove apenas pausas longas.")
        } else if (preset === "balanced") {
            setSilenceThresholdDb(-30)
            setMinSilenceDuration(0.6)
            setSilencePadding(0.15)
            toast.info("Preset Padrão aplicado: ritmo natural e balanceado.")
        } else {
            setSilenceThresholdDb(-25)
            setMinSilenceDuration(0.4)
            setSilencePadding(0.1)
            toast.info(
                "Preset Agressivo aplicado: ritmo acelerado para alta retenção.",
            )
        }
    }

    const handleStart = async () => {
        if (!videoUrl.trim()) {
            toast.error("Por favor, informe a URL do YouTube.")
            return
        }

        let customStartTimeSeconds: number | null = null
        let customEndTimeSeconds: number | null = null

        if (selectionMode === "custom") {
            customStartTimeSeconds = parseTimeToSeconds(customStart)
            customEndTimeSeconds = parseTimeToSeconds(customEnd)

            if (
                customStartTimeSeconds === null ||
                customEndTimeSeconds === null
            ) {
                toast.error(
                    "Informe os horários de início e fim no formato MM:SS ou HH:MM:SS.",
                )
                return
            }

            if (customEndTimeSeconds <= customStartTimeSeconds) {
                toast.error(
                    "O horário final deve ser maior que o horário inicial.",
                )
                return
            }
        }

        const options: PipelineOptions = {
            url: videoUrl.trim(),
            clipping_strategy: "ai",
            transcription_mode: transcriptionMode,
            render_subtitles: false,
            use_heatmap: false,
            is_long_clip: true,
            min_clip_duration: minDurationMinutes * 60,
            max_clip_duration: maxDurationMinutes * 60,
            max_clips: maxClips,
            custom_start_time: customStartTimeSeconds,
            custom_end_time: customEndTimeSeconds,
            remove_silence: removeSilence,
            silence_threshold_db: silenceThresholdDb,
            min_silence_duration: minSilenceDuration,
            silence_padding: silencePadding,
            long_clip_overlay:
                (enableOverlay || Boolean(overlayPath.trim())) &&
                overlayPath.trim()
                    ? overlayPath.trim()
                    : null,
        }

        if (onStartPipeline) {
            await onStartPipeline(options)
        } else {
            const api = await getClipperApi()
            const res = await api.start_pipeline(options)
            if (res.success) {
                toast.success("Processamento iniciado com sucesso!")
            } else {
                toast.error(res.error || "Erro ao iniciar corte.")
            }
        }
    }

    return (
        <div className="space-y-6">
            <Card className="border-border/60 bg-card/60 shadow-md backdrop-blur-sm">
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle className="text-base font-semibold">
                                Link do Episódio Completo
                            </CardTitle>
                            <CardDescription className="text-xs">
                                Formato 16:9 Panorâmico nativo para canais de
                                cortes no YouTube tradicional
                            </CardDescription>
                        </div>
                        <Badge
                            variant="outline"
                            className="border-primary/40 bg-primary/10 text-xs font-semibold text-primary-ink"
                        >
                            16:9 Widescreen
                        </Badge>
                    </div>
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
                        <Button
                            onClick={() => fetchVideoInfo()}
                            disabled={isLoadingInfo || !videoUrl.trim()}
                            className="gap-1.5 text-xs font-semibold"
                        >
                            <MagnifyingGlass size={15} weight="bold" />
                            <span>Buscar</span>
                        </Button>
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
                            Modo de Seleção do Corte Longo
                        </CardTitle>
                        <CardDescription className="text-xs">
                            Escolha se a IA deve encontrar os temas ou se deseja
                            definir o trecho manualmente
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div
                            onClick={() => setSelectionMode("ai")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                selectionMode === "ai"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary-ink">
                                <Sparkle size={18} weight="fill" />
                            </div>
                            <div className="flex-1">
                                <span className="text-xs font-bold text-foreground">
                                    ✨ IA Gemini (Blocos Narrativos Completos)
                                </span>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    A IA identifica conversas com início, debate
                                    e fechamento de raciocínio, gerando títulos
                                    atrativos para vídeos independentes no
                                    YouTube.
                                </p>
                            </div>
                        </div>

                        <div
                            onClick={() => setSelectionMode("custom")}
                            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-all ${
                                selectionMode === "custom"
                                    ? "border-primary bg-primary/10 shadow-xs"
                                    : "border-border/40 bg-muted/20 hover:border-border"
                            }`}
                        >
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                                <Clock size={18} weight="bold" />
                            </div>
                            <div className="flex-1">
                                <span className="text-xs font-bold text-foreground">
                                    ⏱️ Intervalo Personalizado (Início / Fim)
                                </span>
                                <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                                    Você indica os timestamps exatos do vídeo
                                    que deseja recortar e processar.
                                </p>
                            </div>
                        </div>

                        {selectionMode === "custom" && (
                            <div className="mt-2 grid grid-cols-2 gap-3 rounded-lg border border-border/50 bg-background/50 p-3">
                                <div>
                                    <Label className="text-xs">
                                        Início (MM:SS ou HH:MM:SS)
                                    </Label>
                                    <Input
                                        placeholder="05:30"
                                        value={customStart}
                                        onChange={(e) =>
                                            setCustomStart(e.target.value)
                                        }
                                        className="mt-1 h-8 text-xs font-mono"
                                    />
                                </div>
                                <div>
                                    <Label className="text-xs">
                                        Fim (MM:SS ou HH:MM:SS)
                                    </Label>
                                    <Input
                                        placeholder="18:45"
                                        value={customEnd}
                                        onChange={(e) =>
                                            setCustomEnd(e.target.value)
                                        }
                                        className="mt-1 h-8 text-xs font-mono"
                                    />
                                </div>
                            </div>
                        )}
                    </CardContent>
                </Card>

                <Card className="border-border/60 bg-card/60 shadow-md">
                    <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-semibold">
                            Parâmetros de Duração & Quantidade
                        </CardTitle>
                        <CardDescription className="text-xs">
                            Defina os limites de tempo aceitos para os cortes
                            longos
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-xs">
                                <Label>Duração Mínima do Corte</Label>
                                <span className="font-mono font-semibold text-primary-ink">
                                    {minDurationMinutes} min
                                </span>
                            </div>
                            <Slider
                                value={[minDurationMinutes]}
                                onValueChange={(val) =>
                                    setMinDurationMinutes(getSliderValue(val))
                                }
                                min={2}
                                max={15}
                                step={1}
                            />
                        </div>

                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-xs">
                                <Label>Duração Máxima do Corte</Label>
                                <span className="font-mono font-semibold text-primary-ink">
                                    {maxDurationMinutes} min
                                </span>
                            </div>
                            <Slider
                                value={[maxDurationMinutes]}
                                onValueChange={(val) =>
                                    setMaxDurationMinutes(getSliderValue(val))
                                }
                                min={5}
                                max={25}
                                step={1}
                            />
                        </div>

                        <div className="space-y-2">
                            <div className="flex items-center justify-between text-xs">
                                <Label>Quantidade de Cortes a Extrair</Label>
                                <span className="font-mono font-semibold text-primary-ink">
                                    {maxClips} temas
                                </span>
                            </div>
                            <Slider
                                value={[maxClips]}
                                onValueChange={(val) =>
                                    setMaxClips(getSliderValue(val))
                                }
                                min={1}
                                max={5}
                                step={1}
                            />
                        </div>
                    </CardContent>
                </Card>

                <TranscriptionModePicker
                    value={transcriptionMode}
                    onChange={setTranscriptionMode}
                    layout="grid"
                    className="md:col-span-2"
                />
            </div>

            <Card className="border-border/60 bg-card/60 shadow-md">
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <SpeakerSlash
                                size={18}
                                className="text-primary-ink"
                                weight="bold"
                            />
                            <div>
                                <CardTitle className="text-sm font-semibold">
                                    Eliminação Inteligente de Silêncios (Jump
                                    Cut)
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    Remove pausas longas e respirações vazias
                                    para ritmo dinâmico com FFmpeg
                                </CardDescription>
                            </div>
                        </div>
                        <Switch
                            checked={removeSilence}
                            onCheckedChange={setRemoveSilence}
                        />
                    </div>
                </CardHeader>

                {removeSilence && (
                    <CardContent className="space-y-4 pt-1">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-semibold text-muted-foreground">
                                Presets:
                            </span>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => applySilencePreset("soft")}
                                className="h-7 text-xs"
                            >
                                Suave (-35 dB)
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => applySilencePreset("balanced")}
                                className="h-7 text-xs"
                            >
                                Padrão (-30 dB)
                            </Button>
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => applySilencePreset("aggressive")}
                                className="h-7 text-xs"
                            >
                                Agressivo (-25 dB)
                            </Button>
                        </div>

                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                            <div className="space-y-1.5 rounded-lg border border-border/40 bg-muted/20 p-3">
                                <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">
                                        Limite de Ruído
                                    </span>
                                    <span className="font-mono font-semibold">
                                        {silenceThresholdDb} dB
                                    </span>
                                </div>
                                <Slider
                                    value={[silenceThresholdDb]}
                                    onValueChange={(val) =>
                                        setSilenceThresholdDb(
                                            getSliderValue(val),
                                        )
                                    }
                                    min={-45}
                                    max={-20}
                                    step={1}
                                />
                            </div>

                            <div className="space-y-1.5 rounded-lg border border-border/40 bg-muted/20 p-3">
                                <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">
                                        Duração da Pausa
                                    </span>
                                    <span className="font-mono font-semibold">
                                        {minSilenceDuration.toFixed(1)}s
                                    </span>
                                </div>
                                <Slider
                                    value={[minSilenceDuration]}
                                    onValueChange={(val) =>
                                        setMinSilenceDuration(
                                            getSliderValue(val),
                                        )
                                    }
                                    min={0.3}
                                    max={1.5}
                                    step={0.1}
                                />
                            </div>

                            <div className="space-y-1.5 rounded-lg border border-border/40 bg-muted/20 p-3">
                                <div className="flex justify-between text-xs">
                                    <span className="text-muted-foreground">
                                        Margem de Fala (Padding)
                                    </span>
                                    <span className="font-mono font-semibold">
                                        {(silencePadding * 1000).toFixed(0)} ms
                                    </span>
                                </div>
                                <Slider
                                    value={[silencePadding]}
                                    onValueChange={(val) =>
                                        setSilencePadding(getSliderValue(val))
                                    }
                                    min={0.05}
                                    max={0.3}
                                    step={0.02}
                                />
                            </div>
                        </div>
                    </CardContent>
                )}
            </Card>

            <Card className="border-border/60 bg-card/60 shadow-md">
                <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <Image
                                size={18}
                                className="text-primary-ink"
                                weight="bold"
                            />
                            <div>
                                <CardTitle className="text-sm font-semibold">
                                    Overlay de Vídeo (Moldura / Marca D'água
                                    16:9)
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    Sobrepõe moldura artística ou logotipo
                                    PNG/JPG ajustado automaticamente em 16:9
                                </CardDescription>
                            </div>
                        </div>
                        <Switch
                            checked={enableOverlay}
                            onCheckedChange={updateEnableOverlay}
                        />
                    </div>
                </CardHeader>

                {enableOverlay && (
                    <CardContent className="space-y-4 pt-1">
                        <div className="space-y-2">
                            <Label className="text-xs">
                                Imagem de Moldura / Watermark (PNG com
                                transparência ou JPG)
                            </Label>
                            <div className="flex flex-col gap-2 sm:flex-row">
                                <Input
                                    value={overlayPath}
                                    onChange={(event) =>
                                        updateOverlayPath(event.target.value)
                                    }
                                    placeholder="Ex: assets/overlays/frame.png ou C:\Users\...\moldura.png"
                                    className="font-mono text-xs flex-1"
                                />
                                <div className="flex items-center gap-2 shrink-0">
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={handleSelectOverlay}
                                        className="h-9 gap-1.5 text-xs font-semibold"
                                    >
                                        <FolderOpen size={16} />
                                        <span>Procurar...</span>
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        size="sm"
                                        onClick={handleSaveDefaultOverlay}
                                        disabled={
                                            isSavingOverlayDefault ||
                                            !overlayPath.trim() ||
                                            overlayPath.trim() ===
                                                defaultSavedOverlay
                                        }
                                        className="h-9 gap-1.5 text-xs font-semibold"
                                    >
                                        <FloppyDisk size={16} />
                                        <span>
                                            {overlayPath.trim() ===
                                                defaultSavedOverlay &&
                                            defaultSavedOverlay !== ""
                                                ? "Padrão Salvo"
                                                : "Salvar como Padrão"}
                                        </span>
                                    </Button>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                                <span>
                                    Dica: Ao salvar como padrão, o caminho é
                                    persistido no seu arquivo{" "}
                                    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px] text-foreground">
                                        .env
                                    </code>{" "}
                                    como{" "}
                                    <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px] text-foreground">
                                        DEFAULT_LONG_CLIP_OVERLAY
                                    </code>
                                    .
                                </span>
                            </div>
                        </div>
                    </CardContent>
                )}
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
                            ? "Processando Corte Longo..."
                            : "Gerar Cortes Longos (16:9)"}
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
