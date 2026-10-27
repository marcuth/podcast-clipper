import { useState } from "react"
import { Toaster } from "sonner"

import { DiagnosticTab } from "@/components/diagnostic-tab"
import { Header } from "@/components/header"
import { LibraryTab } from "@/components/library-tab"
import { LongClipsTab } from "@/components/long-clips-tab"
import { PipelineMonitorDrawer } from "@/components/pipeline-monitor-drawer"
import { ShortsStudioTab } from "@/components/shorts-studio-tab"
import { Sidebar, type NavigationTab } from "@/components/sidebar"
import { useClipperStatus } from "@/hooks/use-clipper-status"

const PAGE_TITLES: Record<NavigationTab, string> = {
    shorts: "Shorts Studio (9:16)",
    long: "Clipes Longos (16:9)",
    library: "Biblioteca de Projetos & Metadados",
    diagnostics: "Configurações & Manual de Heurísticas",
}

export function App() {
    const [activeTab, setActiveTab] = useState<NavigationTab>("shorts")

    const { isRunning, progress, logs, cancelPipeline, clearLogs } =
        useClipperStatus()

    return (
        <div className="flex h-screen w-screen overflow-hidden bg-background text-foreground antialiased selection:bg-primary/20 selection:text-primary-ink">
            <Sidebar
                activeTab={activeTab}
                onSelectTab={setActiveTab}
                isRunning={isRunning}
                activeModel="gemini-3.8-flash"
            />

            <div className="flex-1 flex flex-col min-w-0 h-screen overflow-y-auto">
                <Header
                    isRunning={isRunning}
                    progress={progress}
                    currentStep={progress.message}
                    geminiModel="gemini-3.8-flash"
                    pageTitle={PAGE_TITLES[activeTab]}
                />

                <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-6 pb-20 flex flex-col gap-6">
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

            <PipelineMonitorDrawer
                isRunning={isRunning}
                progress={progress}
                logs={logs}
                onCancel={cancelPipeline}
                onClearLogs={clearLogs}
            />

            <Toaster richColors position="bottom-right" theme="dark" />
        </div>
    )
}

export default App
