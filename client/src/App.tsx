import { TerminalWindow } from "@phosphor-icons/react"
import { useState } from "react"
import { Toaster } from "sonner"

import { DiagnosticTab } from "@/components/diagnostic-tab"
import { Header } from "@/components/header"
import { LibraryTab } from "@/components/library-tab"
import { LongClipsTab } from "@/components/long-clips-tab"
import { PipelineMonitor } from "@/components/pipeline-monitor"
import { ShortsStudioTab } from "@/components/shorts-studio-tab"
import { Sidebar, type NavigationTab } from "@/components/sidebar"
import { Button } from "@/components/ui/button"
import { useClipperStatus } from "@/hooks/use-clipper-status"

const PAGE_TITLES: Record<NavigationTab, string> = {
    shorts: "Shorts Studio (9:16)",
    long: "Clipes Longos (16:9)",
    library: "Biblioteca de Projetos & Metadados",
    diagnostics: "Configurações & Manual de Heurísticas",
}

export function App() {
    const [activeTab, setActiveTab] = useState<NavigationTab>("shorts")
    const [isTerminalOpen, setIsTerminalOpen] = useState<boolean>(true)

    const { isRunning, progress, logs, cancelPipeline, clearLogs } =
        useClipperStatus()

    return (
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground antialiased selection:bg-primary/20 selection:text-primary-ink">
            <Sidebar
                activeTab={activeTab}
                onSelectTab={setActiveTab}
                isRunning={isRunning}
                activeModel="gemini-2.5-flash"
            />

            <div className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
                <Header
                    isRunning={isRunning}
                    progress={progress}
                    currentStep={progress.message}
                    geminiModel="gemini-2.5-flash"
                    pageTitle={PAGE_TITLES[activeTab]}
                />

                <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-col gap-6">
                    {(isRunning || logs.length > 0) && (
                        <div className="flex flex-col gap-2">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                                    <TerminalWindow className="w-4 h-4 text-primary-ink" />
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

                    {activeTab === "shorts" && (
                        <ShortsStudioTab isPipelineRunning={isRunning} />
                    )}

                    {activeTab === "long" && (
                        <LongClipsTab isPipelineRunning={isRunning} />
                    )}

                    {activeTab === "library" && <LibraryTab />}

                    {activeTab === "diagnostics" && <DiagnosticTab />}
                </main>
            </div>

            <Toaster richColors position="bottom-right" theme="dark" />
        </div>
    )
}

export default App
