"""Load and verify a Blender export bundle (see contracts/export.py and integrations/blender/oc_export.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from onecreations.camera.trajectory import CameraTrajectory
from onecreations.contracts.export import ArrayFile, ExportManifest
from onecreations.hashing import array_digest, content_hash

MANIFEST = "export_manifest.json"


class BundleError(ValueError):
    pass


@dataclass
class ExportBundle:
    root: Path
    manifest: ExportManifest
    raw: dict

    def _load(self, ref: ArrayFile | None, verify: bool = True) -> dict[str, np.ndarray]:
        if ref is None:
            raise BundleError("this bundle has no such array file")
        with np.load(self.root / ref.file, allow_pickle=False) as z:
            arrays = {k: z[k] for k in z.files}
        if sorted(arrays) != sorted(ref.keys):
            raise BundleError(f"{ref.file}: keys {sorted(arrays)} != manifest {sorted(ref.keys)}")
        if verify and array_digest(arrays) != ref.digest:
            raise BundleError(f"{ref.file}: content digest mismatch (file changed after export?)")
        return arrays

    def camera_arrays(self) -> dict[str, np.ndarray]:
        return self._load(self.manifest.camera.samples)

    def objects(self) -> dict[str, np.ndarray]:
        return self._load(self.manifest.objects_file)

    def joints(self) -> dict[str, np.ndarray]:
        return self._load(self.manifest.joints_file)

    def probes(self) -> dict[str, np.ndarray]:
        return self._load(self.manifest.probes_file)

    def passes(self) -> dict[str, np.ndarray]:
        if self.manifest.passes is None:
            raise BundleError("bundle was exported without --passes")
        return self._load(self.manifest.passes.file)

    def K(self) -> np.ndarray:
        return np.asarray(self.manifest.camera.intrinsics.K, dtype=np.float64)

    def image_size(self) -> tuple[int, int]:
        i = self.manifest.camera.intrinsics
        return int(i.resolution_x * i.resolution_percentage / 100), int(i.resolution_y * i.resolution_percentage / 100)

    def camera_trajectory(self) -> CameraTrajectory:
        """Camera over **output** time (what the shot shows, holds included)."""
        a = self.camera_arrays()
        lens = a["lens_mm"] if self.manifest.camera.animated_lens else None
        return CameraTrajectory(a["t"], a["position"], a["quaternion_wxyz"], lens,
                                meta={"provenance": {"source": "blender_export", "confidence": "verified_in_scene"},
                                      "export_content_sha256": self.manifest.content_sha256})


def load_bundle(path: str | Path, verify: bool = True) -> ExportBundle:
    root = Path(path)
    raw = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    manifest = ExportManifest.model_validate(raw)
    if verify:
        body = {k: v for k, v in raw.items() if k != "content_sha256"}
        if content_hash(body) != manifest.content_sha256:
            raise BundleError("manifest content hash mismatch (manifest edited after export?)")
    bundle = ExportBundle(root, manifest, raw)
    if verify:
        for ref in (manifest.camera.samples, manifest.objects_file, manifest.joints_file, manifest.probes_file,
                    manifest.passes.file if manifest.passes else None):
            if ref is not None:
                bundle._load(ref, verify=True)
    return bundle
