"""D1 autonomous director foundation: request -> DirectorPlan -> ShotSpec -> CompiledShot -> existing proven stages.

Blender is an internal deterministic scene engine. Modules: registry (the asset library), actions (semantic events),
camera (presets), policies (processing rules), validate, compiler, prompt (appearance prompt), interpreter (keyword_v1
planner, replaceable by an LLM), planner (plan -> spec), qc (QC as data + preflight evaluator), executor (dry run and
deterministic preflight up to, never including, generation).
"""
