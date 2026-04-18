"""Static prompt for the `genimg character` CLI (character turnaround sheet)."""

# Must satisfy validate_prompt() when used alone (non-empty, >= 3 stripped chars).
CHARACTER_TURNAROUND_PROMPT = """
Studio photo turnaround reference sheet of the person shown in the reference image. Exact facial and hair likeness.

Three panels arranged horizontally on a plain white background.
All panels at identical scale, height alignment, and lighting.

Maintain exact likeness across all panels.
Left panel: front view, facing directly forward.
Middle panel: profile view, facing directly right.
Right panel: rear view, facing directly away.

Relaxed standing pose, arms slightly away from body.
View to thigh in all panels.

Flat, even studio lighting, no cast shadows.
No background, no text, no labels in any panel."""
