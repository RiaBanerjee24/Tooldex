"""
perimeter/core/parser.py
Loads perimeter.yml, validates against Pydantic models, watches for hot-reload.
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Callable, Optional
import yaml
from pydantic import ValidationError
from .models import PerimeterManifest

logger = logging.getLogger("perimeter.parser")


class PerimeterParser:

    def __init__(self, config_path: str = "./perimeter.yml"):
        self.config_path = Path(config_path).resolve()
        self._manifest: Optional[PerimeterManifest] = None
        self._reload_callbacks: list[Callable[[PerimeterManifest], None]] = []

    def load(self) -> PerimeterManifest:
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"perimeter.yml not found at: {self.config_path}\n"
                f"Create a perimeter.yml in your project root or pass --config <path>"
            )
        with open(self.config_path) as f:
            raw = yaml.safe_load(f)
        if not raw:
            raise ValueError("perimeter.yml is empty")
        
        try:
            self._manifest = PerimeterManifest.model_validate(raw)
        except ValidationError as e:
            raise ValueError(f"perimeter.yml validation failed:\n{e}") from e
        logger.info(
            f"Loaded perimeter.yml — {len(self._manifest.agents)} agents, "
            f"{len(self._manifest.servers)} servers, "
            f"{len(self._manifest.policy_engines)} policy engines"
        )
        return self._manifest

    @property
    def manifest(self) -> PerimeterManifest:
        if self._manifest is None:
            return self.load()
        return self._manifest

    def reload(self) -> PerimeterManifest:
        old = self._manifest
        try:
            new = self.load()
            for cb in self._reload_callbacks:
                try:
                    cb(new)
                except Exception as e:
                    logger.error(f"Reload callback error: {e}")
            return new
        except Exception as e:
            logger.error(f"Failed to reload perimeter.yml: {e}")
            if old is not None:
                return old
            raise

    def on_reload(self, callback: Callable[[PerimeterManifest], None]):
        self._reload_callbacks.append(callback)

    async def watch(self):
        try:
            from watchfiles import awatch
        except ImportError:
            logger.warning("Hot reload disabled — pip install watchfiles")
            return
        logger.info(f"Watching {self.config_path} for changes...")
        async for _ in awatch(self.config_path):
            logger.info("perimeter.yml changed — reloading")
            self.reload()

    def validate_references(self) -> list[str]:
        manifest = self.manifest
        warnings: list[str] = []
        server_ids = {s.id for s in manifest.servers}
        engine_ids = {e.id for e in manifest.policy_engines}
        for agent in manifest.agents:
            for srv_ref in agent.servers:
                if srv_ref.ref not in server_ids:
                    warnings.append(
                        f"Agent '{agent.id}' references unknown server '{srv_ref.ref}'"
                    )
            if agent.policy_engine and agent.policy_engine not in engine_ids:
                warnings.append(
                    f"Agent '{agent.id}' references unknown policy engine '{agent.policy_engine}'"
                )
            for policy in agent.policies:
                if policy.ref and policy.ref not in engine_ids:
                    warnings.append(
                        f"Agent '{agent.id}' inline policy references unknown engine '{policy.ref}'"
                    )
        return warnings


# ── singleton ─────────────────────────────────────────────────────────────────

_parser: Optional[PerimeterParser] = None


def get_parser() -> PerimeterParser:
    global _parser
    if _parser is None:
        raise RuntimeError("PerimeterParser not initialized — call init_parser() at startup")
    return _parser


def init_parser(config_path: str) -> PerimeterParser:
    global _parser
    _parser = PerimeterParser(config_path)
    _parser.load()
    return _parser
