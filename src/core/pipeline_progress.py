from dataclasses import dataclass, field


@dataclass
class PipelineProgress:
    step: str  # 'init', 'metadata', 'heatmap', 'download', 'transcribe', 'heuristics', 'clips_plan', 'cutting', 'done', 'error', 'cancelled'
    step_index: int  # 1 to 6
    total_steps: int = 6
    percentage: float = 0.0
    message: str = ""
    current_clip: int = 0
    total_clips: int = 0
    data: dict = field(default_factory=dict)
