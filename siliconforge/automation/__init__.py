"""
siliconforge.automation
======================

Project automation for SiliconForge pipeline.

Implements TODO requirements for:
- Project generator
- YAML parser
- Dependency resolver
- Pipeline manager
- Checkpoint/restart
- Parallel execution
- Progress monitoring
- Failure recovery
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from typing import Callable

import yaml

__all__ = [
    "ProjectConfig",
    "generate_project",
    "parse_yaml_spec",
    "resolve_dependencies",
    "pipeline_manager",
    "save_checkpoint",
    "load_checkpoint",
    "parallel_execute",
    "monitor_progress",
    "recovery_strategy",
]


@dataclass
class ProjectConfig:
    """Project configuration."""

    name: str
    target_frequency_hz: float
    specifications: dict
    corner_configs: list[str]
    output_dir: Path


def generate_project(config: ProjectConfig) -> None:
    """Generate project directory structure with scaffold files."""
    project_path = config.output_dir / config.name
    project_path.mkdir(parents=True, exist_ok=True)

    (project_path / "netlists").mkdir(exist_ok=True)
    (project_path / "spices").mkdir(exist_ok=True)
    (project_path / "rtl").mkdir(exist_ok=True)
    (project_path / "layout").mkdir(exist_ok=True)
    (project_path / "reports").mkdir(exist_ok=True)

    (project_path / "spec.yaml").write_text(
        f"name: {config.name}\ntarget_frequency_hz: {config.target_frequency_hz}\n"
    )
    (project_path / "README.md").write_text(f"# {config.name}\n")
    (project_path / "netlists" / "top.vco.cir").write_text("* VCO netlist template\n")


def parse_yaml_spec(path: Path) -> dict:
    """Parse YAML specification file."""
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_dependencies(modules: dict[str, list[str]]) -> list[str]:
    """Resolve execution order for modules via topological sort.

    Parameters
    ----------
    modules : dict[str, list[str]]
        Mapping of module name -> list of module names it depends on.

    Returns
    -------
    list[str]
        Module names in dependency order.

    Raises
    ------
    ValueError
        If a cycle is detected in the dependency graph.
    """
    order = []
    in_degree = {name: 0 for name in modules}
    adj = {name: [] for name in modules}

    for name, deps in modules.items():
        for dep in deps:
            if dep not in modules:
                raise ValueError(
                    f"Module {name!r} depends on unknown module {dep!r}")
            adj[dep].append(name)
            in_degree[name] += 1

    queue = deque([name for name, deg in in_degree.items() if deg == 0])
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(modules):
        raise ValueError("Cycle detected in module dependency graph")

    return order


def pipeline_manager(
    stages: list[Callable[[], None]],
    checkpoints: bool = True,
    checkpoint_dir: Path | None = None,
) -> None:
    """Execute pipeline stages with checkpoint support."""
    ckpt = checkpoint_dir or Path(".siliconforge_checkpoints")
    ckpt.mkdir(parents=True, exist_ok=True)

    for idx, stage in enumerate(stages):
        try:
            stage()
        except Exception as exc:
            if checkpoints:
                save_checkpoint({"failed_stage": idx, "error": str(
                    exc)}, ckpt / f"stage_{idx}.json")
            raise


def save_checkpoint(state: dict, path: Path) -> None:
    """Save pipeline checkpoint."""
    import json
    with open(path, 'w') as f:
        json.dump(state, f, default=str)


def load_checkpoint(path: Path) -> dict:
    """Load pipeline checkpoint."""
    import json
    with open(path) as f:
        return json.load(f)


def parallel_execute(tasks: list[Callable[[], object]], n_workers: int = 4) -> list:
    """Execute tasks in parallel, re-raising the first exception encountered."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = [None] * len(tasks)

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_to_index = {executor.submit(
            task): i for i, task in enumerate(tasks)}
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                raise RuntimeError(f"Task {idx} failed") from exc

    return results


def monitor_progress(
    stage: str,
    completed: int,
    total: int,
) -> str:
    """Generate progress report."""
    pct = 100 * completed / total if total > 0 else 0
    return f"[{stage}] {completed}/{total} ({pct:.0f}%)"


def recovery_strategy(error: Exception, last_good_checkpoint: Path) -> dict:
    """Generate recovery recommendation."""
    return {
        "error_type": type(error).__name__,
        "last_checkpoint": str(last_good_checkpoint),
        "recovery_action": "rollback" if last_good_checkpoint.exists() else "restart",
    }


__all__ = [
    "ProjectConfig",
    "generate_project",
    "parse_yaml_spec",
    "resolve_dependencies",
    "pipeline_manager",
    "save_checkpoint",
    "load_checkpoint",
    "parallel_execute",
    "monitor_progress",
    "recovery_strategy",
]
