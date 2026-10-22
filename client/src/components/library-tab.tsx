import {
    ArrowsClockwise,
    Clock,
    ClosedCaptioning,
    FileText,
    FilmSlate,
    FloppyDisk,
    FolderOpen,
    Image,
    Play,
    Sparkle,
    Tag,
    YoutubeLogo,
} from "@phosphor-icons/react"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { ClipActionsMenu } from "@/components/clip-actions-menu"
import { ProjectActionsMenu } from "@/components/project-actions-menu"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { getClipperBridge } from "@/lib/bridge"
import type { ClipItem, ProjectItem } from "@/types/api"

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

export function LibraryTab() {
    const [projects, setProjects] = useState<ProjectItem[]>([])
    const [selectedSlug, setSelectedSlug] = useState<string>("")
    const [clips, setClips] = useState<ClipItem[]>([])
    const [isLoadingProjects, setIsLoadingProjects] = useState<boolean>(true)
    const [isLoadingClips, setIsLoadingClips] = useState<boolean>(false)
    const [savingClipName, setSavingClipName] = useState<string | null>(null)
    const [uploadingClipName, setUploadingClipName] = useState<string | null>(
        null,
    )

    const [rerenderClipTarget, setRerenderClipTarget] =
        useState<ClipItem | null>(null)
    const [isRerenderDialogOpen, setIsRerenderDialogOpen] =
        useState<boolean>(false)
    const [rerenderMode, setRerenderMode] = useState<
        "quick_overlay" | "full_rerender"
    >("full_rerender")
    const [rerenderStartTime, setRerenderStartTime] = useState<string>("")
    const [rerenderEndTime, setRerenderEndTime] = useState<string>("")
    const [rerenderRemoveSilence, setRerenderRemoveSilence] =
        useState<boolean>(true)
    const [rerenderOverlayPath, setRerenderOverlayPath] = useState<string>(
        () => {
            if (typeof window !== "undefined") {
                return (
                    localStorage.getItem("podcast_clipper_overlay_path") || ""
                )
            }
            return ""
        },
    )
    const [rerenderEnableOverlay, setRerenderEnableOverlay] = useState<boolean>(
        () => {
            if (typeof window !== "undefined") {
                const saved = localStorage.getItem(
                    "podcast_clipper_overlay_path",
                )
                return Boolean(saved && saved.trim())
            }
            return true
        },
    )
    const [isRerendering, setIsRerendering] = useState<boolean>(false)

    const [clipForms, setClipForms] = useState<
        Record<
            string,
            {
                title: string
                description: string
                tagsString: string
            }
        >
    >({})

    const [subsClipTarget, setSubsClipTarget] = useState<ClipItem | null>(null)
    const [isSubsDialogOpen, setIsSubsDialogOpen] = useState<boolean>(false)
    const [subsStyle, setSubsStyle] = useState<"ass" | "remotion">("ass")
    const [isApplyingSubs, setIsApplyingSubs] = useState<boolean>(false)
    const [thumbClipTarget, setThumbClipTarget] = useState<ClipItem | null>(
        null,
    )
    const [isThumbDialogOpen, setIsThumbDialogOpen] = useState<boolean>(false)
    const [thumbStyle, setThumbStyle] = useState<
        "nano-banana" | "studio-clean" | "classic-viral" | "minimal"
    >("nano-banana")
    const [thumbCustomHook, setThumbCustomHook] = useState<string>("")
    const [thumbCustomBadge, setThumbCustomBadge] = useState<string>("")
    const [thumbCustomColor, setThumbCustomColor] = useState<string>("#FFE500")
    const [thumbRemoveOverlays, setThumbRemoveOverlays] =
        useState<boolean>(true)
    const [generatingThumbClipName, setGeneratingThumbClipName] = useState<
        string | null
    >(null)
    const [isGeneratingAllThumbs, setIsGeneratingAllThumbs] =
        useState<boolean>(false)
    const [clipPreviewMode, setClipPreviewMode] = useState<
        Record<string, "video" | "thumb">
    >({})

    const loadProjects = useCallback(async () => {
        setIsLoadingProjects(true)
        const bridge = getClipperBridge()
        if (!bridge) {
            setIsLoadingProjects(false)
            return
        }

        try {
            const projectList = await bridge.get_projects()
            setProjects(projectList || [])
            if (projectList && projectList.length > 0) {
                const exists = projectList.some(
                    (projectItem: ProjectItem) =>
                        projectItem.slug === selectedSlug,
                )
                if (!exists || !selectedSlug) {
                    setSelectedSlug(projectList[0].slug)
                }
            } else {
                setSelectedSlug("")
                setClips([])
            }
        } catch (error) {
            console.error("Falha ao carregar lista de projetos:", error)
            toast.error("Não foi possível carregar os projetos da biblioteca.")
        } finally {
            setIsLoadingProjects(false)
        }
    }, [selectedSlug])

    const loadClips = useCallback(async (slugToLoad: string) => {
        if (!slugToLoad) {
            setClips([])
            return
        }

        setIsLoadingClips(true)
        const bridge = getClipperBridge()
        if (!bridge) {
            setIsLoadingClips(false)
            return
        }

        try {
            const clipList = await bridge.get_project_clips(slugToLoad)
            setClips(clipList || [])

            const newFormStates: Record<
                string,
                { title: string; description: string; tagsString: string }
            > = {}

            for (const clipItem of clipList || []) {
                newFormStates[clipItem.name] = {
                    title: clipItem.title || "",
                    description: clipItem.description || "",
                    tagsString: (clipItem.tags || []).join(", "),
                }
            }
            setClipForms(newFormStates)
        } catch (error) {
            console.error("Falha ao carregar cortes do projeto:", error)
            toast.error("Erro ao ler arquivos de cortes.")
        } finally {
            setIsLoadingClips(false)
        }
    }, [])

    useEffect(() => {
        loadProjects()
    }, [loadProjects])

    useEffect(() => {
        if (selectedSlug) {
            loadClips(selectedSlug)
        }
    }, [selectedSlug, loadClips])

    const handleReloadClips = async () => {
        if (!selectedSlug) return

        await Promise.all([loadClips(selectedSlug), loadProjects()])
    }

    const handleOpenFolder = async (folderPath?: string) => {
        const bridge = getClipperBridge()
        if (!bridge) return
        const targetDirectory =
            folderPath ||
            projects.find((projectItem) => projectItem.slug === selectedSlug)
                ?.path ||
            ""
        if (!targetDirectory) return

        try {
            await bridge.open_folder(targetDirectory)
            toast.success("Pasta aberta no Explorador de Arquivos")
        } catch {
            toast.error("Erro ao abrir pasta")
        }
    }

    const handleOpenExternalVideo = async (videoFilePath: string | null) => {
        if (!videoFilePath) return
        const bridge = getClipperBridge()
        if (!bridge) return

        try {
            await bridge.open_video(videoFilePath)
            toast.success("Abrindo vídeo no player padrão do Windows")
        } catch {
            toast.error("Erro ao abrir player de vídeo")
        }
    }

    const handleFieldChange = (
        clipName: string,
        field: "title" | "description" | "tagsString",
        value: string,
    ) => {
        setClipForms((previousState) => ({
            ...previousState,
            [clipName]: {
                ...previousState[clipName],
                [field]: value,
            },
        }))
    }

    const handleSaveMetadata = async (clip: ClipItem) => {
        const bridge = getClipperBridge()
        if (!bridge || !selectedSlug) return

        const formData = clipForms[clip.name]
        if (!formData) return

        setSavingClipName(clip.name)

        const tagsArray = formData.tagsString
            .split(",")
            .map((tagItem) => tagItem.trim())
            .filter((tagItem) => tagItem.length > 0)

        const payload = {
            title: formData.title,
            description: formData.description,
            tags: tagsArray,
            viral_score: clip.score,
            hook: clip.hook,
        }

        try {
            const response = await bridge.update_clip_details(
                selectedSlug,
                clip.name,
                payload,
            )
            if (response.success) {
                toast.success(
                    `Metadados de "${formData.title}" salvos com sucesso!`,
                )
            } else {
                toast.error(response.error || "Erro ao salvar metadados.")
            }
        } catch {
            toast.error("Falha ao comunicar com o backend.")
        } finally {
            setSavingClipName(null)
        }
    }

    const handleCopyMetadata = (clip: ClipItem) => {
        const formData = clipForms[clip.name]
        if (!formData) return

        const formattedText = `TITULO:\n${formData.title}\n\nDESCRICAO:\n${formData.description}\n\nTAGS:\n${formData.tagsString}`

        navigator.clipboard.writeText(formattedText)
        toast.success(
            "Título, descrição e tags copiados para a área de transferência!",
        )
    }

    const handleUploadToYouTube = async (clip: ClipItem) => {
        const bridge = getClipperBridge()

        if (!bridge || !selectedSlug) return

        setUploadingClipName(clip.name)

        toast.info(`Iniciando upload de "${clip.title}" para o YouTube...`)

        try {
            const response = await bridge.upload_clip_to_youtube(
                selectedSlug,
                clip.name,
                "public",
            )
            if (response.success && response.video_url) {
                toast.success(
                    `Vídeo publicado com sucesso! Link: ${response.video_url}`,
                    {
                        duration: 10000,
                    },
                )
            } else {
                toast.error(response.error || "Erro ao publicar no YouTube.")
            }
        } catch (error) {
            toast.error(`Falha no upload para o YouTube: ${String(error)}`)
        } finally {
            setUploadingClipName(null)
        }
    }

    const handleOpenRerenderModal = (clip: ClipItem) => {
        setRerenderClipTarget(clip)
        setRerenderStartTime(
            clip.start_formatted ||
                `${Math.floor(clip.start / 60)}:${Math.floor(clip.start % 60)
                    .toString()
                    .padStart(2, "0")}`,
        )
        setRerenderEndTime(
            clip.end_formatted ||
                `${Math.floor(clip.end / 60)}:${Math.floor(clip.end % 60)
                    .toString()
                    .padStart(2, "0")}`,
        )
        const savedPath =
            typeof window !== "undefined"
                ? localStorage.getItem("podcast_clipper_overlay_path") || ""
                : ""
        if (savedPath) {
            setRerenderOverlayPath(savedPath)
            setRerenderEnableOverlay(true)
        }
        setRerenderMode(clip.rendered ? "full_rerender" : "full_rerender")
        setIsRerenderDialogOpen(true)
    }

    const handleSelectRerenderOverlay = async () => {
        const bridge = getClipperBridge()
        if (!bridge) return
        try {
            const result = await bridge.select_overlay_file()
            if (result.success && result.file_path) {
                setRerenderOverlayPath(result.file_path)
                setRerenderEnableOverlay(true)
                if (typeof window !== "undefined") {
                    localStorage.setItem(
                        "podcast_clipper_overlay_path",
                        result.file_path,
                    )
                    localStorage.setItem(
                        "podcast_clipper_enable_overlay",
                        "true",
                    )
                }
                toast.success("Arquivo de overlay selecionado com sucesso!")
            }
        } catch {
            toast.error("Erro ao selecionar arquivo de overlay.")
        }
    }

    const handleExecuteRerender = async () => {
        if (!rerenderClipTarget || !selectedSlug) return
        const bridge = getClipperBridge()
        if (!bridge) return

        setIsRerendering(true)
        try {
            if (
                rerenderMode === "quick_overlay" &&
                rerenderClipTarget.rendered
            ) {
                if (!rerenderOverlayPath.trim()) {
                    toast.error(
                        "Selecione um arquivo de imagem para aplicar como overlay.",
                    )
                    setIsRerendering(false)
                    return
                }
                toast.info(
                    `Aplicando overlay no clipe ${rerenderClipTarget.name}...`,
                )
                const res = await bridge.apply_clip_overlay(
                    selectedSlug,
                    rerenderClipTarget.name,
                    rerenderOverlayPath.trim(),
                )
                if (res.success) {
                    toast.success(
                        res.message || "Overlay aplicado com sucesso!",
                    )
                    setIsRerenderDialogOpen(false)
                    await loadClips(selectedSlug)
                } else {
                    toast.error(res.error || "Erro ao aplicar overlay.")
                }
            } else {
                const parsedStart = parseTimeToSeconds(rerenderStartTime)
                const parsedEnd = parseTimeToSeconds(rerenderEndTime)

                toast.info(
                    `Iniciando renderização de ${rerenderClipTarget.name}...`,
                )
                const optionsPayload: Record<string, unknown> = {
                    start: parsedStart ?? rerenderClipTarget.start,
                    end: parsedEnd ?? rerenderClipTarget.end,
                    remove_silence: rerenderRemoveSilence,
                    overlay_image_path:
                        rerenderEnableOverlay && rerenderOverlayPath.trim()
                            ? rerenderOverlayPath.trim()
                            : null,
                    is_long_clip: selectedProject
                        ? !selectedProject.name.toLowerCase().includes("shorts")
                        : true,
                }
                const res = await bridge.rerender_clip(
                    selectedSlug,
                    rerenderClipTarget.name,
                    optionsPayload,
                )
                if (res.success) {
                    toast.success(
                        res.message || "Vídeo re-renderizado com sucesso!",
                    )
                    setIsRerenderDialogOpen(false)
                    await loadClips(selectedSlug)
                } else {
                    toast.error(res.error || "Erro na re-renderização.")
                }
            }
        } catch (err) {
            toast.error(`Falha na renderização: ${String(err)}`)
        } finally {
            setIsRerendering(false)
        }
    }

    const handleOpenSubsModal = (clip: ClipItem) => {
        setSubsClipTarget(clip)
        setSubsStyle("ass")
        setIsSubsDialogOpen(true)
    }

    const handleApplySubtitles = async () => {
        if (!subsClipTarget || !selectedSlug) return
        const bridge = getClipperBridge()
        if (!bridge) return

        setIsApplyingSubs(true)
        const toastId = toast.loading(
            `Transcrevendo e aplicando legendas em ${subsClipTarget.name}... (pode levar alguns minutos)`,
        )

        try {
            const res = await bridge.apply_clip_subtitles(
                selectedSlug,
                subsClipTarget.name,
                subsStyle,
            )
            if (res.success) {
                toast.success(res.message || "Legendas aplicadas!", {
                    id: toastId,
                })
                setIsSubsDialogOpen(false)
                await loadClips(selectedSlug)
            } else {
                toast.error(res.error || "Falha ao aplicar legendas.", {
                    id: toastId,
                })
            }
        } catch (err) {
            toast.error(`Erro ao aplicar legendas: ${String(err)}`, {
                id: toastId,
            })
        } finally {
            setIsApplyingSubs(false)
        }
    }

    const handleOpenThumbModal = (clip: ClipItem) => {
        setThumbClipTarget(clip)
        setThumbCustomHook(clip.hook || "")
        setThumbCustomBadge("EXCLUSIVO")
        setThumbCustomColor("#FFE500")
        setThumbStyle("nano-banana")
        setThumbRemoveOverlays(true)
        setIsThumbDialogOpen(true)
    }

    const handleGenerateThumbnail = async () => {
        if (!thumbClipTarget || !selectedSlug) return

        const bridge = getClipperBridge()
        if (!bridge) {
            toast.error("API nativa do PyWebView não disponível.")
            return
        }

        const clipName = thumbClipTarget.name
        setGeneratingThumbClipName(clipName)
        const toastId = toast.loading(
            `Gerando thumbnail com IA para ${clipName}...`,
        )

        try {
            const res = await bridge.generate_clip_thumbnail(
                selectedSlug,
                clipName,
                {
                    style: thumbStyle,
                    custom_hook: thumbCustomHook.trim() || undefined,
                    custom_badge: thumbCustomBadge.trim() || undefined,
                    custom_color: thumbCustomColor.trim() || undefined,
                    remove_overlays: thumbRemoveOverlays,
                },
            )

            if (res.success) {
                toast.success("Thumbnail gerada com sucesso!", { id: toastId })
                setClips((prev) =>
                    prev.map((c) =>
                        c.name === clipName
                            ? {
                                  ...c,
                                  thumbnail_url:
                                      res.thumbnail_url || c.thumbnail_url,
                                  thumbnail_path:
                                      res.thumbnail_path || c.thumbnail_path,
                              }
                            : c,
                    ),
                )
                setClipPreviewMode((prev) => ({ ...prev, [clipName]: "thumb" }))
                setIsThumbDialogOpen(false)
            } else {
                toast.error(res.error || "Falha ao gerar thumbnail.", {
                    id: toastId,
                })
            }
        } catch (err) {
            toast.error(`Erro ao gerar thumbnail: ${err}`, { id: toastId })
        } finally {
            setGeneratingThumbClipName(null)
        }
    }

    const handleGenerateAllThumbnails = async () => {
        if (!selectedSlug || clips.length === 0) return
        const bridge = getClipperBridge()
        if (!bridge) return

        setIsGeneratingAllThumbs(true)
        const toastId = toast.loading(
            `Gerando thumbnails com IA para todos os ${clips.length} cortes...`,
        )

        try {
            const res = await bridge.generate_all_project_thumbnails(
                selectedSlug,
                {
                    style: "nano-banana",
                    remove_overlays: true,
                },
            )

            if (res.success) {
                toast.success(
                    res.message || "Thumbnails geradas com sucesso!",
                    {
                        id: toastId,
                    },
                )
                await loadClips(selectedSlug)
            } else {
                toast.error(
                    res.error || "Erro ao gerar thumbnails do projeto.",
                    { id: toastId },
                )
            }
        } catch (err) {
            toast.error(`Erro: ${err}`, { id: toastId })
        } finally {
            setIsGeneratingAllThumbs(false)
        }
    }

    const selectedProject = projects.find(
        (projectItem) => projectItem.slug === selectedSlug,
    )

    return (
        <div className="flex flex-col gap-6">
            <Card className="border-border/60 bg-card/60 backdrop-blur-md">
                <CardContent className="p-4 sm:p-6 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 flex-1">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm font-medium">
                            <FilmSlate className="w-5 h-5 text-primary-ink" />
                            <span>Projeto:</span>
                        </div>

                        {isLoadingProjects ? (
                            <Skeleton className="h-10 w-full sm:w-[320px]" />
                        ) : projects.length === 0 ? (
                            <div className="text-sm text-muted-foreground italic">
                                Nenhum projeto gerado ainda na pasta output/.
                            </div>
                        ) : (
                            <div className="relative flex-1 sm:max-w-[420px]">
                                <select
                                    value={selectedSlug}
                                    onChange={(event) =>
                                        setSelectedSlug(event.target.value)
                                    }
                                    className="w-full h-10 px-3 py-2 rounded-md bg-background border border-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition"
                                >
                                    {projects.map((projectItem) => (
                                        <option
                                            key={projectItem.slug}
                                            value={projectItem.slug}
                                        >
                                            {projectItem.name} (
                                            {projectItem.clips_count} cortes)
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}

                        <Button
                            variant="outline"
                            size="icon"
                            onClick={loadProjects}
                            disabled={isLoadingProjects}
                            title="Recarregar projetos"
                            className="shrink-0"
                        >
                            <ArrowsClockwise
                                className={`w-4 h-4 ${isLoadingProjects ? "animate-spin" : ""}`}
                            />
                        </Button>
                    </div>

                    <div className="flex items-center gap-2">
                        {selectedProject && (
                            <>
                                {selectedProject.is_timestamps_only ? (
                                    <Badge
                                        variant="outline"
                                        className="border-amber-500/40 text-amber-400 bg-amber-500/10 px-2.5 py-1"
                                    >
                                        Modo Timestamps (Sem Vídeo)
                                    </Badge>
                                ) : (
                                    <Badge
                                        variant="outline"
                                        className="border-emerald-500/40 text-emerald-400 bg-emerald-500/10 px-2.5 py-1"
                                    >
                                        Vídeos Renderizados
                                    </Badge>
                                )}

                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={handleReloadClips}
                                    disabled={isLoadingClips}
                                    title="Recarregar os vídeos deste projeto"
                                    className="gap-2"
                                >
                                    <ArrowsClockwise
                                        className={`w-4 h-4 ${isLoadingClips ? "animate-spin" : ""}`}
                                    />
                                    <span>Recarregar Vídeos</span>
                                </Button>

                                <ProjectActionsMenu
                                    isGeneratingThumbnails={
                                        isGeneratingAllThumbs
                                    }
                                    hasClips={clips.length > 0}
                                    onGenerateAllThumbnails={
                                        handleGenerateAllThumbnails
                                    }
                                    onOpenFolder={() =>
                                        handleOpenFolder(selectedProject.path)
                                    }
                                />
                            </>
                        )}
                    </div>
                </CardContent>
            </Card>

            {isLoadingClips ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <Skeleton className="h-[480px] rounded-xl" />
                    <Skeleton className="h-[480px] rounded-xl" />
                </div>
            ) : clips.length === 0 ? (
                <Card className="border-dashed border-border/70 bg-card/20 py-16 text-center">
                    <CardContent className="flex flex-col items-center justify-center gap-3">
                        <FilmSlate className="w-12 h-12 text-muted-foreground/40 stroke-1" />
                        <h3 className="text-lg font-medium text-foreground">
                            Nenhum corte encontrado
                        </h3>
                        <p className="text-sm text-muted-foreground max-w-md">
                            Selecione outro projeto acima ou gere novos cortes
                            usando as abas Shorts Studio (9:16) ou Cortes Longos
                            (16:9).
                        </p>
                    </CardContent>
                </Card>
            ) : (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    {clips.map((clipItem, clipIndex) => {
                        const currentForm = clipForms[clipItem.name] || {
                            title: clipItem.title || "",
                            description: clipItem.description || "",
                            tagsString: (clipItem.tags || []).join(", "),
                        }

                        const isSaving = savingClipName === clipItem.name

                        return (
                            <Card
                                key={clipItem.name}
                                className="border-border/60 bg-card/40 backdrop-blur-md flex flex-col overflow-hidden transition-all hover:border-primary/40 shadow-sm"
                            >
                                <CardHeader className="p-4 sm:p-5 bg-muted/20 border-b border-border/40 flex flex-row items-center justify-between gap-2">
                                    <div className="flex items-center gap-2">
                                        <Badge
                                            variant="secondary"
                                            className="font-mono text-xs"
                                        >
                                            #{clipIndex + 1}
                                        </Badge>
                                        <CardTitle className="text-base font-semibold truncate max-w-[240px] sm:max-w-[320px]">
                                            {clipItem.name}
                                        </CardTitle>
                                    </div>

                                    <div className="flex items-center gap-2 shrink-0">
                                        {clipItem.score > 0 && (
                                            <Badge
                                                variant="outline"
                                                className="gap-1 border-primary/40 text-primary-ink bg-primary/10 text-xs font-semibold"
                                            >
                                                <Sparkle className="w-3.5 h-3.5" />
                                                <span>
                                                    Score: {clipItem.score}
                                                </span>
                                            </Badge>
                                        )}

                                        <Badge
                                            variant="secondary"
                                            className="gap-1 text-xs text-muted-foreground font-mono"
                                        >
                                            <Clock className="w-3 h-3" />
                                            <span>
                                                {clipItem.start_formatted &&
                                                clipItem.end_formatted
                                                    ? `${clipItem.start_formatted} - ${clipItem.end_formatted}`
                                                    : `${clipItem.duration}s`}
                                            </span>
                                        </Badge>

                                        <ClipActionsMenu
                                            clip={clipItem}
                                            isGeneratingThumbnail={
                                                generatingThumbClipName ===
                                                clipItem.name
                                            }
                                            onGenerateThumbnail={() =>
                                                handleOpenThumbModal(clipItem)
                                            }
                                            onRerender={() =>
                                                handleOpenRerenderModal(
                                                    clipItem,
                                                )
                                            }
                                            onApplySubtitles={() =>
                                                handleOpenSubsModal(clipItem)
                                            }
                                            onOpenExternalPlayer={() =>
                                                handleOpenExternalVideo(
                                                    clipItem.video_path,
                                                )
                                            }
                                            onOpenThumbnailFile={() =>
                                                handleOpenFolder(
                                                    clipItem.thumbnail_path ??
                                                        undefined,
                                                )
                                            }
                                            onCopyMetadata={() =>
                                                handleCopyMetadata(clipItem)
                                            }
                                        />
                                    </div>
                                </CardHeader>

                                <CardContent className="p-4 sm:p-6 flex flex-col gap-5 flex-1">
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-1 bg-muted/40 p-0.5 rounded-lg border border-border/40">
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    setClipPreviewMode(
                                                        (prev) => ({
                                                            ...prev,
                                                            [clipItem.name]:
                                                                "video",
                                                        }),
                                                    )
                                                }
                                                className={`text-xs px-2.5 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
                                                    (clipPreviewMode[
                                                        clipItem.name
                                                    ] ?? "video") === "video"
                                                        ? "bg-background text-foreground shadow-xs font-semibold"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <FilmSlate className="w-3.5 h-3.5" />
                                                <span>Vídeo</span>
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() =>
                                                    setClipPreviewMode(
                                                        (prev) => ({
                                                            ...prev,
                                                            [clipItem.name]:
                                                                "thumb",
                                                        }),
                                                    )
                                                }
                                                className={`text-xs px-2.5 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
                                                    clipPreviewMode[
                                                        clipItem.name
                                                    ] === "thumb"
                                                        ? "bg-background text-foreground shadow-xs font-semibold"
                                                        : "text-muted-foreground hover:text-foreground"
                                                }`}
                                            >
                                                <Image className="w-3.5 h-3.5 text-amber-400" />
                                                <span>Thumbnail 16:9</span>
                                                {clipItem.thumbnail_url && (
                                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                                )}
                                            </button>
                                        </div>

                                        {clipItem.thumbnail_url &&
                                            clipPreviewMode[clipItem.name] ===
                                                "thumb" && (
                                                <Badge
                                                    variant="outline"
                                                    className="text-[10px] text-emerald-400 border-emerald-500/30 bg-emerald-500/10 py-0.5"
                                                >
                                                    1280x720 HD
                                                </Badge>
                                            )}
                                    </div>

                                    {clipPreviewMode[clipItem.name] ===
                                    "thumb" ? (
                                        clipItem.thumbnail_url ? (
                                            <div className="flex flex-col gap-2">
                                                <div className="relative rounded-lg overflow-hidden bg-black/80 aspect-video flex items-center justify-center border border-border/40 group">
                                                    <img
                                                        src={
                                                            clipItem.thumbnail_url
                                                        }
                                                        alt={`Thumbnail ${clipItem.name}`}
                                                        className="w-full h-full object-cover"
                                                    />
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="rounded-lg border border-dashed border-border/80 bg-muted/15 p-6 flex flex-col items-center justify-center gap-3 aspect-video text-center">
                                                <Image className="w-8 h-8 text-muted-foreground/40" />
                                                <div className="text-xs text-muted-foreground max-w-xs">
                                                    Nenhuma thumbnail gerada
                                                    ainda para este corte.
                                                </div>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() =>
                                                        handleOpenThumbModal(
                                                            clipItem,
                                                        )
                                                    }
                                                    disabled={
                                                        generatingThumbClipName ===
                                                        clipItem.name
                                                    }
                                                    className="gap-1.5 text-xs text-amber-400 border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 font-semibold"
                                                >
                                                    <Sparkle
                                                        className={`w-3.5 h-3.5 ${generatingThumbClipName === clipItem.name ? "animate-spin" : ""}`}
                                                    />
                                                    <span>
                                                        Gerar Thumbnail com IA
                                                    </span>
                                                </Button>
                                            </div>
                                        )
                                    ) : clipItem.rendered &&
                                      clipItem.video_url ? (
                                        <div className="flex flex-col gap-2">
                                            <div className="relative rounded-lg overflow-hidden bg-black/80 aspect-video flex items-center justify-center border border-border/40">
                                                <video
                                                    src={clipItem.video_url}
                                                    controls
                                                    preload="metadata"
                                                    className="w-full h-full object-contain max-h-[300px]"
                                                />
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="rounded-lg border border-dashed border-border/80 bg-muted/15 p-4 flex flex-col gap-2">
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                                                    <Clock className="w-4 h-4 text-primary-ink" />
                                                    <span>
                                                        Intervalo no Vídeo
                                                        Original:
                                                    </span>
                                                </div>
                                                <Badge
                                                    variant="outline"
                                                    className="font-mono text-xs"
                                                >
                                                    {clipItem.start_formatted} →{" "}
                                                    {clipItem.end_formatted} (
                                                    {clipItem.duration}s)
                                                </Badge>
                                            </div>

                                            {clipItem.hook && (
                                                <div className="mt-2 p-2.5 rounded bg-primary/10 border border-primary/20 text-xs">
                                                    <span className="font-semibold text-primary-ink block mb-0.5">
                                                        Gancho / Hook Viral:
                                                    </span>
                                                    <p className="text-foreground/90 italic">
                                                        "{clipItem.hook}"
                                                    </p>
                                                </div>
                                            )}

                                            <div className="flex items-center justify-end pt-1">
                                                <Button
                                                    variant="default"
                                                    size="sm"
                                                    onClick={() =>
                                                        handleOpenRerenderModal(
                                                            clipItem,
                                                        )
                                                    }
                                                    className="text-xs gap-1.5 h-8 font-semibold"
                                                >
                                                    <Play className="w-3.5 h-3.5" />
                                                    <span>
                                                        Renderizar Vídeo Agora
                                                    </span>
                                                </Button>
                                            </div>
                                        </div>
                                    )}

                                    <div className="flex flex-col gap-3.5 flex-1">
                                        <div className="flex flex-col gap-1.5">
                                            <Label className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                                                <FileText className="w-3.5 h-3.5" />
                                                <span>Título do Corte</span>
                                            </Label>
                                            <Input
                                                value={currentForm.title}
                                                onChange={(event) =>
                                                    handleFieldChange(
                                                        clipItem.name,
                                                        "title",
                                                        event.target.value,
                                                    )
                                                }
                                                placeholder="Título atraente para o YouTube..."
                                                className="text-sm font-medium bg-background/50"
                                            />
                                        </div>

                                        <div className="flex flex-col gap-1.5">
                                            <Label className="text-xs font-semibold text-muted-foreground">
                                                Descrição & Hashtags
                                            </Label>
                                            <textarea
                                                rows={3}
                                                value={currentForm.description}
                                                onChange={(event) =>
                                                    handleFieldChange(
                                                        clipItem.name,
                                                        "description",
                                                        event.target.value,
                                                    )
                                                }
                                                placeholder="Descrição do corte com chamada para ação..."
                                                className="w-full px-3 py-2 text-xs rounded-md bg-background/50 border border-input text-foreground focus:outline-none focus:ring-2 focus:ring-primary resize-y"
                                            />
                                        </div>

                                        <div className="flex flex-col gap-1.5">
                                            <Label className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                                                <Tag className="w-3.5 h-3.5" />
                                                <span>
                                                    Tags (separadas por vírgula)
                                                </span>
                                            </Label>
                                            <Input
                                                value={currentForm.tagsString}
                                                onChange={(event) =>
                                                    handleFieldChange(
                                                        clipItem.name,
                                                        "tagsString",
                                                        event.target.value,
                                                    )
                                                }
                                                placeholder="podcast, viral, reflexão, desenvolvimento"
                                                className="text-xs bg-background/50"
                                            />
                                        </div>
                                    </div>

                                    <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/40">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Button
                                                variant="secondary"
                                                size="sm"
                                                disabled={
                                                    uploadingClipName ===
                                                        clipItem.name ||
                                                    !clipItem.rendered
                                                }
                                                onClick={() =>
                                                    handleUploadToYouTube(
                                                        clipItem,
                                                    )
                                                }
                                                className="gap-2 text-xs"
                                                title="Fazer upload deste corte para o canal do YouTube configurado"
                                            >
                                                <YoutubeLogo
                                                    className="w-3.5 h-3.5 text-red-500"
                                                    weight="fill"
                                                />
                                                <span>
                                                    {uploadingClipName ===
                                                    clipItem.name
                                                        ? "Enviando..."
                                                        : "Enviar ao YouTube"}
                                                </span>
                                            </Button>
                                        </div>

                                        <Button
                                            size="sm"
                                            onClick={() =>
                                                handleSaveMetadata(clipItem)
                                            }
                                            disabled={isSaving}
                                            className="gap-2 text-xs"
                                        >
                                            <FloppyDisk
                                                className={`w-3.5 h-3.5 ${isSaving ? "animate-pulse" : ""}`}
                                            />
                                            <span>
                                                {isSaving
                                                    ? "Salvando..."
                                                    : "Salvar Alterações"}
                                            </span>
                                        </Button>
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })}
                </div>
            )}

            <Dialog
                open={isRerenderDialogOpen}
                onOpenChange={(open) =>
                    !isRerendering && setIsRerenderDialogOpen(open)
                }
            >
                <DialogContent className="sm:max-w-md bg-card/95 backdrop-blur-xl border-border/80">
                    <DialogHeader>
                        <div className="flex items-center gap-2">
                            <ArrowsClockwise className="w-5 h-5 text-primary-ink" />
                            <DialogTitle className="text-base font-semibold">
                                Re-renderizar {rerenderClipTarget?.name}
                            </DialogTitle>
                        </div>
                        <DialogDescription className="text-xs">
                            Ajuste os parâmetros de corte, remoção de silêncio
                            ou aplique a moldura 16:9 diretamente.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="flex flex-col gap-4 py-2 text-xs">
                        {rerenderClipTarget?.rendered && (
                            <div className="flex rounded-lg border border-border/60 bg-muted/20 p-1">
                                <button
                                    type="button"
                                    onClick={() =>
                                        setRerenderMode("full_rerender")
                                    }
                                    className={`flex-1 py-1.5 px-3 rounded-md text-xs font-semibold transition ${
                                        rerenderMode === "full_rerender"
                                            ? "bg-background text-foreground shadow-xs"
                                            : "text-muted-foreground hover:text-foreground"
                                    }`}
                                >
                                    Re-renderizar Completo
                                </button>
                                <button
                                    type="button"
                                    onClick={() =>
                                        setRerenderMode("quick_overlay")
                                    }
                                    className={`flex-1 py-1.5 px-3 rounded-md text-xs font-semibold transition ${
                                        rerenderMode === "quick_overlay"
                                            ? "bg-background text-foreground shadow-xs"
                                            : "text-muted-foreground hover:text-foreground"
                                    }`}
                                >
                                    Aplicar Overlay Rápido (3s)
                                </button>
                            </div>
                        )}

                        {rerenderMode === "full_rerender" && (
                            <>
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="flex flex-col gap-1.5">
                                        <Label className="text-xs">
                                            Início (MM:SS ou HH:MM:SS)
                                        </Label>
                                        <Input
                                            value={rerenderStartTime}
                                            onChange={(e) =>
                                                setRerenderStartTime(
                                                    e.target.value,
                                                )
                                            }
                                            placeholder="Ex: 17:41"
                                            className="font-mono text-xs"
                                        />
                                    </div>
                                    <div className="flex flex-col gap-1.5">
                                        <Label className="text-xs">
                                            Fim (MM:SS ou HH:MM:SS)
                                        </Label>
                                        <Input
                                            value={rerenderEndTime}
                                            onChange={(e) =>
                                                setRerenderEndTime(
                                                    e.target.value,
                                                )
                                            }
                                            placeholder="Ex: 18:50"
                                            className="font-mono text-xs"
                                        />
                                    </div>
                                </div>

                                <div className="flex items-center justify-between p-3 rounded-lg border border-border/40 bg-muted/20">
                                    <div className="flex flex-col">
                                        <span className="font-semibold text-foreground">
                                            Remover Silêncios (Jump Cut)
                                        </span>
                                        <span className="text-[11px] text-muted-foreground">
                                            Corta pausas e respirações vazias
                                            automaticamente
                                        </span>
                                    </div>
                                    <Switch
                                        checked={rerenderRemoveSilence}
                                        onCheckedChange={
                                            setRerenderRemoveSilence
                                        }
                                    />
                                </div>
                            </>
                        )}

                        <div className="p-3 rounded-lg border border-border/40 bg-muted/20 flex flex-col gap-2.5">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-1.5">
                                    <Image className="w-4 h-4 text-primary-ink" />
                                    <span className="font-semibold text-foreground">
                                        Overlay 16:9 (Moldura / Watermark)
                                    </span>
                                </div>
                                <Switch
                                    checked={rerenderEnableOverlay}
                                    onCheckedChange={setRerenderEnableOverlay}
                                />
                            </div>

                            {rerenderEnableOverlay && (
                                <div className="flex gap-2">
                                    <Input
                                        value={rerenderOverlayPath}
                                        onChange={(e) => {
                                            setRerenderOverlayPath(
                                                e.target.value,
                                            )
                                            if (typeof window !== "undefined") {
                                                localStorage.setItem(
                                                    "podcast_clipper_overlay_path",
                                                    e.target.value,
                                                )
                                            }
                                        }}
                                        placeholder="Caminho do arquivo PNG/JPG da moldura..."
                                        className="font-mono text-xs flex-1"
                                    />
                                    <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={handleSelectRerenderOverlay}
                                        className="gap-1.5 text-xs font-semibold shrink-0"
                                    >
                                        <FolderOpen className="w-3.5 h-3.5" />
                                        <span>Procurar...</span>
                                    </Button>
                                </div>
                            )}
                        </div>
                    </div>

                    <DialogFooter className="flex items-center justify-end gap-2 pt-2">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={isRerendering}
                            onClick={() => setIsRerenderDialogOpen(false)}
                            className="text-xs"
                        >
                            Cancelar
                        </Button>
                        <Button
                            size="sm"
                            disabled={isRerendering}
                            onClick={handleExecuteRerender}
                            className="text-xs font-semibold gap-1.5"
                        >
                            <ArrowsClockwise
                                className={`w-3.5 h-3.5 ${isRerendering ? "animate-spin" : ""}`}
                            />
                            <span>
                                {isRerendering
                                    ? "Processando..."
                                    : rerenderMode === "quick_overlay"
                                      ? "Aplicar Overlay"
                                      : "Iniciar Re-renderização"}
                            </span>
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog
                open={isSubsDialogOpen}
                onOpenChange={(open) =>
                    !isApplyingSubs && setIsSubsDialogOpen(open)
                }
            >
                <DialogContent className="sm:max-w-md bg-card/95 backdrop-blur-xl border-border/80">
                    <DialogHeader>
                        <div className="flex items-center gap-2">
                            <ClosedCaptioning className="w-5 h-5 text-primary-ink" />
                            <DialogTitle className="text-base font-semibold">
                                Aplicar legendas em {subsClipTarget?.name}
                            </DialogTitle>
                        </div>
                        <DialogDescription className="text-xs">
                            O áudio do corte é transcrito com o Whisper local e
                            as legendas dinâmicas são queimadas no vídeo. O
                            vídeo original é mantido, então você pode trocar o
                            estilo depois sem duplicar legendas.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="flex flex-col gap-1.5 py-2 text-xs">
                        <Label className="text-xs">Estilo das legendas</Label>
                        <select
                            value={subsStyle}
                            disabled={isApplyingSubs}
                            onChange={(event) =>
                                setSubsStyle(
                                    event.target.value as "ass" | "remotion",
                                )
                            }
                            className="w-full h-10 px-3 py-2 rounded-md bg-background border border-input text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition"
                        >
                            <option value="ass">
                                Padrão (rápido, sem dependências extras)
                            </option>
                            <option value="remotion">
                                Remotion (animação palavra a palavra, requer
                                Node)
                            </option>
                        </select>
                    </div>

                    <DialogFooter className="flex items-center justify-end gap-2 pt-2">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={isApplyingSubs}
                            onClick={() => setIsSubsDialogOpen(false)}
                            className="text-xs"
                        >
                            Cancelar
                        </Button>
                        <Button
                            size="sm"
                            disabled={isApplyingSubs}
                            onClick={handleApplySubtitles}
                            className="text-xs font-semibold gap-1.5"
                        >
                            <ClosedCaptioning
                                className={`w-3.5 h-3.5 ${isApplyingSubs ? "animate-pulse" : ""}`}
                            />
                            <span>
                                {isApplyingSubs
                                    ? "Processando..."
                                    : "Aplicar Legendas"}
                            </span>
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog
                open={isThumbDialogOpen}
                onOpenChange={setIsThumbDialogOpen}
            >
                <DialogContent className="sm:max-w-[560px] bg-card border-border/80">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-lg font-bold">
                            <Sparkle className="w-5 h-5 text-amber-400" />
                            <span>Gerar Thumbnail com IA</span>
                        </DialogTitle>
                        <DialogDescription className="text-xs text-muted-foreground">
                            Crie capas personalizadas em formato 16:9 (1280x720)
                            com alto CTR para o YouTube, removendo rodapés
                            nativos e QR codes.
                        </DialogDescription>
                    </DialogHeader>

                    {thumbClipTarget && (
                        <div className="flex flex-col gap-4 py-2 text-sm">
                            {thumbClipTarget.thumbnail_url && (
                                <div className="relative rounded-lg overflow-hidden bg-black/80 aspect-video border border-border/60">
                                    <img
                                        src={thumbClipTarget.thumbnail_url}
                                        alt="Thumbnail Preview"
                                        className="w-full h-full object-cover"
                                    />
                                    <Badge
                                        variant="secondary"
                                        className="absolute top-2 right-2 text-[10px] bg-black/70 text-white backdrop-blur-xs"
                                    >
                                        Atual
                                    </Badge>
                                </div>
                            )}

                            <div className="flex flex-col gap-2">
                                <Label className="text-xs font-semibold text-muted-foreground">
                                    Estilo Visual da Thumbnail
                                </Label>
                                <div className="grid grid-cols-2 gap-2">
                                    <button
                                        type="button"
                                        onClick={() =>
                                            setThumbStyle("nano-banana")
                                        }
                                        className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                                            thumbStyle === "nano-banana"
                                                ? "border-amber-500 bg-amber-500/10 text-foreground"
                                                : "border-border/60 bg-muted/20 hover:border-border text-muted-foreground"
                                        }`}
                                    >
                                        <div className="font-semibold text-xs flex items-center gap-1.5 text-foreground">
                                            <span>🍌</span>
                                            <span>Nano Banana (IA)</span>
                                        </div>
                                        <p className="text-[11px] leading-tight opacity-80">
                                            Inpainting multimodal e gancho de
                                            alto impacto gerado por IA.
                                        </p>
                                    </button>

                                    <button
                                        type="button"
                                        onClick={() =>
                                            setThumbStyle("studio-clean")
                                        }
                                        className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                                            thumbStyle === "studio-clean"
                                                ? "border-primary bg-primary/10 text-foreground"
                                                : "border-border/60 bg-muted/20 hover:border-border text-muted-foreground"
                                        }`}
                                    >
                                        <div className="font-semibold text-xs flex items-center gap-1.5 text-foreground">
                                            <span>🎬</span>
                                            <span>Estúdio Limpo</span>
                                        </div>
                                        <p className="text-[11px] leading-tight opacity-80">
                                            Corta rodapé/superchat e limpa QR
                                            codes (100% offline).
                                        </p>
                                    </button>

                                    <button
                                        type="button"
                                        onClick={() =>
                                            setThumbStyle("classic-viral")
                                        }
                                        className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                                            thumbStyle === "classic-viral"
                                                ? "border-primary bg-primary/10 text-foreground"
                                                : "border-border/60 bg-muted/20 hover:border-border text-muted-foreground"
                                        }`}
                                    >
                                        <div className="font-semibold text-xs flex items-center gap-1.5 text-foreground">
                                            <span>⚡</span>
                                            <span>Clássico Viral</span>
                                        </div>
                                        <p className="text-[11px] leading-tight opacity-80">
                                            Letras garrafais em amarelo/neon com
                                            sombra e selo.
                                        </p>
                                    </button>

                                    <button
                                        type="button"
                                        onClick={() => setThumbStyle("minimal")}
                                        className={`p-3 rounded-lg border text-left flex flex-col gap-1 transition-all ${
                                            thumbStyle === "minimal"
                                                ? "border-primary bg-primary/10 text-foreground"
                                                : "border-border/60 bg-muted/20 hover:border-border text-muted-foreground"
                                        }`}
                                    >
                                        <div className="font-semibold text-xs flex items-center gap-1.5 text-foreground">
                                            <span>🎯</span>
                                            <span>Minimalista</span>
                                        </div>
                                        <p className="text-[11px] leading-tight opacity-80">
                                            Cena limpa dos participantes sem
                                            textos gigantes.
                                        </p>
                                    </button>
                                </div>
                            </div>

                            <div className="p-3 rounded-lg border border-border/40 bg-muted/20 flex items-center justify-between">
                                <div className="flex flex-col gap-0.5">
                                    <span className="font-semibold text-xs text-foreground">
                                        Remover QR Codes e Rodapés Nativos
                                    </span>
                                    <span className="text-[11px] text-muted-foreground">
                                        Re-enquadra e aplica inpainting para
                                        remover superchats da base
                                    </span>
                                </div>
                                <Switch
                                    checked={thumbRemoveOverlays}
                                    onCheckedChange={setThumbRemoveOverlays}
                                />
                            </div>

                            {thumbStyle !== "minimal" &&
                                thumbStyle !== "studio-clean" && (
                                    <div className="flex flex-col gap-3 p-3 rounded-lg border border-border/40 bg-muted/20">
                                        <div className="flex flex-col gap-1.5">
                                            <div className="flex items-center justify-between">
                                                <Label className="text-xs font-semibold text-muted-foreground">
                                                    Frase de Gancho (Hook Text)
                                                </Label>
                                                <span className="text-[10px] text-muted-foreground">
                                                    Deixe vazio para a IA gerar
                                                    automaticamente
                                                </span>
                                            </div>
                                            <Input
                                                value={thumbCustomHook}
                                                onChange={(e) =>
                                                    setThumbCustomHook(
                                                        e.target.value,
                                                    )
                                                }
                                                placeholder='Ex: "450 NÃO LEEM?!", "REVELOU O SEGREDO!"'
                                                className="text-xs font-bold uppercase"
                                            />
                                        </div>

                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="flex flex-col gap-1.5">
                                                <Label className="text-xs font-semibold text-muted-foreground">
                                                    Selo / Badge
                                                </Label>
                                                <Input
                                                    value={thumbCustomBadge}
                                                    onChange={(e) =>
                                                        setThumbCustomBadge(
                                                            e.target.value,
                                                        )
                                                    }
                                                    placeholder="Ex: EXPOSTO, URGENTE"
                                                    className="text-xs font-semibold uppercase"
                                                />
                                            </div>

                                            <div className="flex flex-col gap-1.5">
                                                <Label className="text-xs font-semibold text-muted-foreground">
                                                    Cor do Texto
                                                </Label>
                                                <div className="flex items-center gap-1.5">
                                                    {[
                                                        "#FFE500",
                                                        "#FF2A2A",
                                                        "#00FFAA",
                                                        "#00D2FF",
                                                        "#FFFFFF",
                                                    ].map((c) => (
                                                        <button
                                                            key={c}
                                                            type="button"
                                                            onClick={() =>
                                                                setThumbCustomColor(
                                                                    c,
                                                                )
                                                            }
                                                            className={`w-6 h-6 rounded-md border transition-all ${
                                                                thumbCustomColor ===
                                                                c
                                                                    ? "ring-2 ring-primary scale-110"
                                                                    : "border-border/60 hover:scale-105"
                                                            }`}
                                                            style={{
                                                                backgroundColor:
                                                                    c,
                                                            }}
                                                        />
                                                    ))}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}
                        </div>
                    )}

                    <DialogFooter className="flex items-center justify-end gap-2 pt-2">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={generatingThumbClipName !== null}
                            onClick={() => setIsThumbDialogOpen(false)}
                            className="text-xs"
                        >
                            Cancelar
                        </Button>
                        <Button
                            size="sm"
                            disabled={generatingThumbClipName !== null}
                            onClick={handleGenerateThumbnail}
                            className="text-xs font-semibold gap-1.5 bg-amber-500 hover:bg-amber-600 text-black"
                        >
                            <Sparkle
                                className={`w-3.5 h-3.5 ${generatingThumbClipName !== null ? "animate-spin" : ""}`}
                            />
                            <span>
                                {generatingThumbClipName !== null
                                    ? "Gerando com IA..."
                                    : "Gerar Thumbnail"}
                            </span>
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
