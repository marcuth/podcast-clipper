export interface VideoInfo {
    title: string
    thumbnail: string
    duration: number
    author: string
    views: number
}

export type ClippingStrategy = "ai" | "heuristics"
export type CaptionStyle = "ass" | "remotion"
export type TranscriptionMode =
    "assemblyai" | "whisper" | "yt_full" | "yt_partial"

export interface PipelineOptions {
    url: string
    clipping_strategy: ClippingStrategy
    transcription_mode: TranscriptionMode
    use_heatmap?: boolean
    render_subtitles?: boolean
    use_whisper_subtitles?: boolean
    caption_style?: CaptionStyle
    apply_vignette?: boolean
    vignette_angle?: string
    enable_split_screen?: boolean
    split_screen_chance?: number
    only_timestamps?: boolean
    is_long_clip?: boolean
    remove_silence?: boolean
    silence_threshold_db?: number
    min_silence_duration?: number
    silence_padding?: number
    min_clip_duration?: number
    max_clip_duration?: number
    max_clips?: number
    custom_start_time?: number | null
    custom_end_time?: number | null
    delete_original_video?: boolean
    long_clip_overlay?: string | null
}

export interface ProgressData {
    step: string
    step_index: number
    percentage: number
    message: string
    current_clip: number
    total_clips: number
    data?: Record<string, unknown>
}

export interface LogItem {
    level: "info" | "warning" | "error"
    message: string
}

export interface ProjectItem {
    slug: string
    name: string
    clips_count: number
    modified_at: number
    path: string
    is_timestamps_only: boolean
}

export interface ClipDetails {
    title: string
    description: string
    tags: string[]
    hook?: string
    viral_score?: number
}

export interface ClipItem {
    name: string
    video_file: string | null
    video_url: string | null
    video_path: string | null
    details_path: string
    score: number
    duration: number
    start: number
    end: number
    start_formatted: string
    end_formatted: string
    title: string
    description: string
    tags: string[]
    hook?: string
    rendered: boolean
    thumbnail_file?: string | null
    thumbnail_url?: string | null
    thumbnail_path?: string | null
}

export interface SystemInfo {
    python_version: string
    os: string
    gemini_configured: boolean
    gemini_key_preview: string
    gemini_model?: string
    assemblyai_configured?: boolean
    assemblyai_key_preview?: string
    face_model_available: boolean
    workspace_dir: string
    output_dir: string
    default_long_clip_overlay?: string
    has_default_overlay?: boolean
}

export interface ClipperApi {
    get_video_info(
        url: string,
    ): Promise<{ success: boolean; data?: VideoInfo; error?: string }>
    start_pipeline(
        options: PipelineOptions,
    ): Promise<{ success: boolean; message?: string; error?: string }>
    cancel_pipeline(): Promise<{ success: boolean; message: string }>
    get_status(): Promise<{
        is_running: boolean
        progress: ProgressData
        logs: LogItem[]
    }>
    get_projects(): Promise<ProjectItem[]>
    get_project_clips(slug: string): Promise<ClipItem[]>
    update_clip_details(
        slug: string,
        clip_name: string,
        details: ClipDetails,
    ): Promise<{ success: boolean; message?: string; error?: string }>
    open_folder(target_path: string): Promise<boolean>
    open_video(video_path: string): Promise<boolean>
    get_system_info(): Promise<SystemInfo>
    save_assemblyai_api_key(
        api_key: string,
    ): Promise<{ success: boolean; message?: string; error?: string }>
    save_gemini_api_key(
        api_key: string,
    ): Promise<{ success: boolean; message?: string; error?: string }>
    save_gemini_model(
        model_name: string,
    ): Promise<{ success: boolean; message?: string; error?: string }>
    select_overlay_file(): Promise<{
        success: boolean
        file_path?: string
        cancelled?: boolean
        error?: string
    }>
    save_default_long_clip_overlay(
        overlay_path: string,
    ): Promise<{ success: boolean; message?: string; error?: string }>
    get_youtube_status(): Promise<{
        success: boolean
        data?: {
            is_configured: boolean
            is_authenticated: boolean
            client_secrets_file: string
            credentials_storage_file: string
        }
        error?: string
    }>
    upload_clip_to_youtube(
        slug: string,
        clip_name: string,
        privacy?: string,
        category?: string,
        schedule_time?: string | null,
    ): Promise<{
        success: boolean
        video_id?: string
        video_url?: string
        title?: string
        error?: string
    }>
    save_youtube_client_secret(
        client_secret_json: string,
    ): Promise<{ success: boolean; message?: string; error?: string }>
    apply_clip_overlay(
        slug: string,
        clip_name: string,
        overlay_path: string,
    ): Promise<{
        success: boolean
        message?: string
        error?: string
        video_url?: string
    }>
    apply_clip_subtitles(
        slug: string,
        clip_name: string,
        caption_style?: CaptionStyle,
    ): Promise<{
        success: boolean
        message?: string
        error?: string
        video_url?: string
    }>
    rerender_clip(
        slug: string,
        clip_name: string,
        options?: Record<string, unknown>,
    ): Promise<{
        success: boolean
        message?: string
        error?: string
        video_url?: string
    }>
    generate_clip_thumbnail(
        slug: string,
        clip_name: string,
        options?: Record<string, unknown>,
    ): Promise<{
        success: boolean
        message?: string
        error?: string
        thumbnail_url?: string
        thumbnail_path?: string
        hook_text?: string
        badge_text?: string
        color?: string
    }>
    generate_all_project_thumbnails(
        slug: string,
        options?: Record<string, unknown>,
    ): Promise<{
        success: boolean
        message?: string
        error?: string
        generated_count?: number
        total_clips?: number
        errors?: string[]
    }>
}

declare global {
    interface Window {
        pywebview?: {
            api: ClipperApi
        }
        __clipperBridge?: {
            listeners: Record<string, Array<(data: unknown) => void>>
            on: (event: string, callback: (data: unknown) => void) => void
            off: (event: string, callback: (data: unknown) => void) => void
            emit: (event: string, data: unknown) => void
        }
    }
}
