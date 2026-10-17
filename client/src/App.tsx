import {
    DeviceMobileCamera,
    FolderSimpleStar,
    GearSix,
    MonitorPlay,
    TerminalWindow,
} from "@phosphor-icons/react"
import { useState } from "react"
import { Toaster } from "sonner"

import { DiagnosticTab } from "@/components/diagnostic-tab"
import { Header } from "@/components/header"
import { LibraryTab } from "@/components/library-tab"
import { LongClipsTab } from "@/components/long-clips-tab"
import { PipelineMonitor } from "@/components/pipeline-monitor"
import { ShortsStudioTab } from "@/components/shorts-studio-tab"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useClipperStatus } from "@/hooks/use-clipper-status"

type NavigationTab = "shorts" | "long" | "library" | "diagnostics"

export function App() {
    const [activeTab, setActiveTab] = useState<NavigationTab>("shorts")
    const [isTerminalOpen, setIsTerminalOpen] = useState<boolean>(true)

    const { isRunning, progress, logs, cancelPipeline, clearLogs } =
        useClipperStatus()

    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col antialiased selection:bg-primary/20 selection:text-primary">
            {/* Top Navigation & Status Bar */}
            <Header
                isRunning={isRunning}
                currentStep={progress.message}
                geminiModel="gemini-2.5-flash"
            />

            {/* Main Application Container */}
            <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-col gap-6">
                {/* Pipeline Real-time Progress & Terminal Monitor */}
                {(isRunning || logs.length > 0) && (
                    <div className="flex flex-col gap-2">
                        <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                                <TerminalWindow className="w-4 h-4 text-primary" />
                                <span>Monitor de Execução do Pipeline</span>
                            </span>
                            <Button
                                variant="ghost"
                                size="sm"
                                onClick={() =>
                                    setIsTerminalOpen(
                                        (previousValue) => !previousValue,
                                    )
                                }
                                className="h-7 text-xs text-muted-foreground hover:text-foreground"
                            >
                                {isTerminalOpen
                                    ? "Ocultar Painel"
                                    : "Exibir Painel"}
                            </Button>
                        </div>

                        {isTerminalOpen && (
                            <PipelineMonitor
                                progress={progress}
                                isRunning={isRunning}
                                logs={logs}
                                onCancel={cancelPipeline}
                                onClearLogs={clearLogs}
                            />
                        )}
                    </div>
                )}

                {/* Studio Tab Navigation */}
                <Tabs
                    value={activeTab}
                    onValueChange={(value) =>
                        setActiveTab(value as NavigationTab)
                    }
                    className="flex flex-col gap-6"
                >
                    <div className="border-b border-border/60 pb-3 flex items-center justify-between">
                        <TabsList className="bg-muted/40 p-1 rounded-xl border border-border/40 gap-1">
                            <TabsTrigger
                                value="shorts"
                                className="gap-2 px-3 py-1.5 rounded-lg text-xs font-medium data-active:bg-background data-active:shadow-sm"
                            >
                                <DeviceMobileCamera className="w-4 h-4 text-primary" />
                                <span>Shorts Studio (9:16)</span>
                            </TabsTrigger>

                            <TabsTrigger
                                value="long"
                                className="gap-2 px-3 py-1.5 rounded-lg text-xs font-medium data-active:bg-background data-active:shadow-sm"
                            >
                                <MonitorPlay className="w-4 h-4 text-cyan-400" />
                                <span>Cortes Longos (16:9)</span>
                            </TabsTrigger>

                            <TabsTrigger
                                value="library"
                                className="gap-2 px-3 py-1.5 rounded-lg text-xs font-medium data-active:bg-background data-active:shadow-sm"
                            >
                                <FolderSimpleStar className="w-4 h-4 text-amber-400" />
                                <span>Biblioteca & Metadados</span>
                            </TabsTrigger>

                            <TabsTrigger
                                value="diagnostics"
                                className="gap-2 px-3 py-1.5 rounded-lg text-xs font-medium data-active:bg-background data-active:shadow-sm"
                            >
                                <GearSix className="w-4 h-4 text-emerald-400" />
                                <span>Configurações & Heurísticas</span>
                            </TabsTrigger>
                        </TabsList>
                    </div>

                    {/* Tab 1: Shorts Studio 9:16 */}
                    <TabsContent value="shorts">
                        <ShortsStudioTab isPipelineRunning={isRunning} />
                    </TabsContent>

                    {/* Tab 2: Long Clips 16:9 */}
                    <TabsContent value="long">
                        <LongClipsTab isPipelineRunning={isRunning} />
                    </TabsContent>

                    {/* Tab 3: Library & Metadata */}
                    <TabsContent value="library">
                        <LibraryTab />
                    </TabsContent>

                    {/* Tab 4: Diagnostics & Viral Heuristics Manual */}
                    <TabsContent value="diagnostics">
                        <DiagnosticTab />
                    </TabsContent>
                </Tabs>
            </main>

            {/* Global Toast Notifications */}
            <Toaster richColors position="bottom-right" theme="dark" />
        </div>
    )
}

export default App
