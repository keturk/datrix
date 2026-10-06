"""Generate one example project for one registered language, as ``datrix generate`` would.

The cross-target repo gates read generated SOURCE TEXT only, never compiled output, so they
run the pipeline at ``ValidationLevel.FAST``: it still fixes imports and formats files but
skips the language's own toolchain compile step, which is an unrelated, more expensive
dependency for a check that reads text.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

DEFAULT_PROFILE: Final[str] = "test"


def generate_example(language: str, source: Path, output_dir: Path, profile: str = DEFAULT_PROFILE) -> Path:
    """Generate *source* for *language* into a fresh *output_dir* through the real ``GenerationPipeline``.

    Args:
        language: A ``datrix.languages`` entry-point name.
        source: The example's ``system.dtrx``.
        output_dir: Destination; removed first so a previous run's files never read as this one's.
        profile: The configuration profile to resolve.

    Returns:
        *output_dir*.

    Raises:
        RuntimeError: The pipeline reported failure; the message carries its error text.
    """
    from datrix_cli.generation.validation_level import ValidationLevel
    from datrix_cli.pipeline.contract import PipelineConfig
    from datrix_cli.pipeline.generation import GenerationPipeline
    from datrix_common.plugin.identity import LanguageId
    from datrix_language.registration import register_all

    # Parsing real `.dtrx` needs the stdlib parser protocol registered, which the CLI entry
    # point normally does once at startup; a gate calls the pipeline directly.
    register_all()
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True)
    result = GenerationPipeline().run(
        source,
        output_dir,
        PipelineConfig(
            target_language=LanguageId(language),
            profile=profile,
            validation_level=ValidationLevel.FAST,
        ),
    )
    if not result.success:
        raise RuntimeError(
            f"Generating {source} for language {language!r} failed: "
            f"{'; '.join(result.errors) or 'success=False, no error text'}"
        )
    return output_dir
