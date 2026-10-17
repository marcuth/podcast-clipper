"""
Heuristic: boost a segment's score based on YouTube's "most replayed"
heatmap intensity.

The heatmap is a list of time windows, each with a normalised intensity
score (0–1).  For every segment we compute the average intensity of all
windows that overlap with the segment and apply a weighted bonus.

Score contribution:
    +3.0  × average_intensity   (max +3.0 at intensity = 1.0)

This makes highly-replayed sections significantly more likely to be chosen
as clips without completely overriding the text-based heuristics.
"""

from domain.segment import Segment

HEATMAP_BOOST = 3.0  # maximum bonus points when intensity == 1.0


def score_heatmap(segment: Segment, heatmap: list[dict]) -> None:
    """
    Mutate *segment.score* in-place by adding a heat-map intensity bonus.

    Args:
        segment: The transcript segment to score.
        heatmap: List of dicts with keys ``start``, ``end``, ``intensity``
                 as returned by ``get_youtube_heatmap()``.  May be empty,
                 in which case this function is a no-op.
    """
    if not heatmap:
        return

    overlapping_intensities: list[float] = []

    for window in heatmap:
        # Check for any overlap between the segment and the heatmap window.
        overlap_start = max(segment.start, window["start"])
        overlap_end   = min(segment.end,   window["end"])

        if overlap_end > overlap_start:
            overlapping_intensities.append(window["intensity"])

    if not overlapping_intensities:
        return

    avg_intensity = sum(overlapping_intensities) / len(overlapping_intensities)
    segment.score += HEATMAP_BOOST * avg_intensity
