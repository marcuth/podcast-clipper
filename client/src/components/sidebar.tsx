import {
    DeviceMobileCamera,
    FilmSlate,
    FolderOpen,
    FolderSimpleStar,
    GearSix,
    MonitorPlay,
    Sparkle,
} from "@phosphor-icons/react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { getClipperBridge } from "@/lib/bridge"

export type NavigationTab = "shorts" | "long" | "library" | "diagnostics"

interface NavigationItem {
    id: NavigationTab
    label: string
    description: string
    icon: typeof DeviceMobileCamera
    accentColor: string
}

const NAVIGATION_ITEMS: NavigationItem[] = [
    {
        id: "shorts",
        label: "Shorts",
        description: "Formato 9:16 com Face-Tracking",
        icon: DeviceMobileCamera,
        accentColor: "text-primary",
    },
    {
        id: "long",
        label: "Clipes Longos",
        description: "Formato 16:9 e Remoção de Silêncio",
        icon: MonitorPlay,
        accentColor: "text-cyan-400",
    },
    {
        id: "library",
        label: "Biblioteca",
        description: "Projetos, Cortes e Metadados",
        icon: FolderSimpleStar,
        accentColor: "text-amber-400",
    },
    {
        id: "diagnostics",
        label: "Configurações",
        description: "IA Gemini, Diagnóstico e Heurísticas",
        icon: GearSix,
        accentColor: "text-emerald-400",
    },
]

interface SidebarProps {
    activeTab: NavigationTab
    onSelectTab: (tab: NavigationTab) => void
    isRunning: boolean
    activeModel?: string
}

export function Sidebar({
    activeTab,
    onSelectTab,
    isRunning,
    activeModel = "gemini-2.5-flash",
}: SidebarProps) {
    const handleOpenOutputFolder = async () => {
        const bridge = getClipperBridge()
        if (!bridge) return

        try {
            const systemInfo = await bridge.get_system_info()

            if (systemInfo?.output_dir) {
                await bridge.open_folder(systemInfo.output_dir)
                toast.success("Pasta de saída aberta no Explorador de Arquivos")
            }
        } catch {
            toast.error("Erro ao abrir pasta de saída")
        }
    }

    return (
        <aside className="w-64 shrink-0 border-r border-border/60 bg-card/50 backdrop-blur-xl flex flex-col justify-between h-screen sticky top-0 z-30 select-none">
            {/* Top Branding */}
            <div className="flex flex-col">
                <div className="h-16 px-5 border-b border-border/40 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary via-purple-600 to-indigo-600 text-white shadow-md shadow-primary/25">
                            <FilmSlate size={22} weight="duotone" />
                        </div>
                        <div className="flex flex-col">
                            <span className="font-bold text-base tracking-tight text-foreground leading-tight">
                                Podcast Clipper
                            </span>
                            <span className="text-[10px] text-muted-foreground uppercase font-semibold tracking-wider">
                                By Marcuth
                            </span>
                        </div>
                    </div>

                    <Badge
                        variant="secondary"
                        className="text-[10px] font-mono px-1.5 py-0 h-4 bg-primary/10 text-primary border-primary/20"
                    >
                        v2.5
                    </Badge>
                </div>

                {/* Navigation Items */}
                <nav className="p-3 space-y-1.5 flex flex-col">
                    <span className="px-3 pt-3 pb-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                        Menu Principal
                    </span>

                    {NAVIGATION_ITEMS.map((item) => {
                        const IconComponent = item.icon
                        const isActive = activeTab === item.id

                        return (
                            <button
                                key={item.id}
                                type="button"
                                onClick={() => onSelectTab(item.id)}
                                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all relative group ${
                                    isActive
                                        ? "bg-primary/15 text-foreground font-semibold shadow-sm border border-primary/25"
                                        : "text-muted-foreground hover:text-foreground hover:bg-muted/30 border border-transparent"
                                }`}
                            >
                                <div
                                    className={`flex items-center justify-center w-8 h-8 rounded-lg transition ${
                                        isActive
                                            ? "bg-primary text-primary-foreground shadow-sm"
                                            : "bg-muted/40 group-hover:bg-muted text-foreground/80"
                                    }`}
                                >
                                    <IconComponent
                                        size={18}
                                        weight={isActive ? "fill" : "duotone"}
                                        className={
                                            isActive
                                                ? "text-primary-foreground"
                                                : item.accentColor
                                        }
                                    />
                                </div>

                                <div className="flex flex-col flex-1 min-w-0">
                                    <span className="text-xs truncate">
                                        {item.label}
                                    </span>
                                    <span className="text-[10px] text-muted-foreground truncate font-normal">
                                        {item.description}
                                    </span>
                                </div>

                                {isActive && (
                                    <span className="absolute right-2 w-1.5 h-4 rounded-full bg-primary" />
                                )}
                            </button>
                        )
                    })}
                </nav>
            </div>

            {/* Bottom System & Output Bar */}
            <div className="p-3 border-t border-border/40 flex flex-col gap-2 bg-muted/10">
                {/* Status Indicator */}
                <div className="flex items-center justify-between px-2 py-1 text-xs">
                    <span className="text-muted-foreground text-[11px]">
                        Status:
                    </span>
                    {isRunning ? (
                        <div className="flex items-center gap-1.5 text-primary text-[11px] font-medium">
                            <span className="relative flex h-2 w-2">
                                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75"></span>
                                <span className="relative inline-flex h-2 w-2 rounded-full bg-primary"></span>
                            </span>
                            <span>Processando</span>
                        </div>
                    ) : (
                        <div className="flex items-center gap-1.5 text-emerald-400 text-[11px] font-medium">
                            <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
                            <span>Pronto</span>
                        </div>
                    )}
                </div>

                {/* Gemini Model Info */}
                <div className="flex items-center justify-between px-2 py-1 rounded-lg bg-background/50 border border-border/30 text-[11px]">
                    <span className="flex items-center gap-1 text-muted-foreground">
                        <Sparkle size={13} className="text-primary" />
                        <span>IA:</span>
                    </span>
                    <span className="font-mono text-foreground font-medium truncate max-w-[120px]">
                        {activeModel}
                    </span>
                </div>

                {/* Quick Folder Button */}
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleOpenOutputFolder}
                    className="w-full justify-start gap-2 h-8 text-xs text-muted-foreground hover:text-foreground"
                >
                    <FolderOpen size={15} />
                    <span>Abrir Pasta Output</span>
                </Button>
            </div>
        </aside>
    )
}
