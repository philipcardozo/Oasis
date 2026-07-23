"""Server-persisted Map Studio slots: list, get, update, rename, reset,
duplicate, set-active, export, import. Owner-only, validated, optimistic
concurrency via a version field.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server import repositories as repo
from server.config import Settings, get_settings
from server.db import get_db
from server.deps import require_csrf, require_user
from server.models import MapSlot, User
from server.observability import correlation_id

log = logging.getLogger("oasis.mapslots")
router = APIRouter(prefix="/api/map-slots", tags=["map-slots"])

# Allowlist — never trust an arbitrary client-provided style URL.
ALLOWED_BASEMAPS = {"standard", "dark", "satellite"}
ALLOWED_LAYERS = {
    "relief-terrain", "relief-hillshade", "companies", "securities", "relationships",
    "industrial-energy", "industrial-power-plants", "relief-crime", "marketplace",
}
ALLOWED_CONDITIONS = {"clouds", "storms", "precipitation", "temperature", "wind", "wildfire", "floods", "radar"}


class SlotUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    basemap: str | None = None
    config: dict | None = None
    version: int  # optimistic concurrency — client must send the version it read


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: int


class ImportIn(BaseModel):
    slot_number: int = Field(ge=1, le=3)
    config_json: str = Field(max_length=200_000)


def _sanitize_text(value: str) -> str:
    # Strip angle brackets to prevent stored XSS via names/descriptions.
    return value.replace("<", "").replace(">", "").strip()


def _validate_config(config: dict, settings: Settings) -> dict:
    if not isinstance(config, dict):
        raise HTTPException(422, "config must be an object")
    if len(json.dumps(config)) > settings.max_map_config_bytes:
        raise HTTPException(413, "map configuration too large")

    out: dict = {}
    layers = config.get("layers")
    if layers is not None:
        if not isinstance(layers, dict):
            raise HTTPException(422, "layers must be an object")
        bad = set(layers) - ALLOWED_LAYERS
        if bad:
            raise HTTPException(422, f"unknown layer(s): {sorted(bad)}")
        out["layers"] = {k: bool(v) for k, v in layers.items()}

    cam = config.get("camera")
    if cam is not None:
        if not isinstance(cam, dict):
            raise HTTPException(422, "camera must be an object")
        c = {}
        if "center" in cam:
            center = cam["center"]
            if (not isinstance(center, (list, tuple)) or len(center) != 2
                    or not all(isinstance(x, (int, float)) for x in center)
                    or not (-180 <= center[0] <= 180) or not (-90 <= center[1] <= 90)):
                raise HTTPException(422, "camera.center must be [lng,lat] within bounds")
            c["center"] = [float(center[0]), float(center[1])]
        for key, lo, hi in (("zoom", 0, 24), ("bearing", -360, 360), ("pitch", 0, 85)):
            if key in cam:
                v = cam[key]
                if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                    raise HTTPException(422, f"camera.{key} out of range [{lo},{hi}]")
                c[key] = float(v)
        out["camera"] = c

    conditions = config.get("conditions")
    if conditions is not None:
        if not isinstance(conditions, dict):
            raise HTTPException(422, "conditions must be an object")
        bad = set(conditions) - ALLOWED_CONDITIONS
        if bad:
            raise HTTPException(422, f"unknown condition(s): {sorted(bad)}")
        out["conditions"] = {k: bool(v) for k, v in conditions.items()}

    prefs = config.get("prefs")
    if isinstance(prefs, dict):
        # Opacity / numeric prefs bounded; unknown keys dropped.
        opacity = prefs.get("opacity")
        if opacity is not None and (not isinstance(opacity, (int, float)) or not (0 <= opacity <= 1)):
            raise HTTPException(422, "prefs.opacity must be within [0,1]")
        out["prefs"] = {k: v for k, v in prefs.items() if isinstance(v, (int, float, bool, str)) and len(str(v)) < 200}

    return out


def _slot_dto(slot: MapSlot) -> dict:
    return {
        "id": slot.id, "slot_number": slot.slot_number, "name": slot.name,
        "description": slot.description, "basemap": slot.basemap, "config": slot.config,
        "version": slot.version, "is_active": slot.is_active,
        "updated_at": slot.updated_at.isoformat(),
    }


def _require_slot(db: Session, user: User, slot_id: str) -> MapSlot:
    slot = repo.get_map_slot(db, user.id, slot_id)
    if not slot:
        raise HTTPException(404, "map slot not found")
    return slot


def _check_version(slot: MapSlot, client_version: int) -> None:
    if client_version != slot.version:
        raise HTTPException(409, {"error": "version_conflict", "current_version": slot.version})


@router.get("")
def list_slots(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return {"slots": [_slot_dto(s) for s in repo.list_map_slots(db, user.id)]}


@router.get("/{slot_id}")
def get_slot(slot_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _slot_dto(_require_slot(db, user, slot_id))


@router.put("/{slot_id}")
def update_slot(slot_id: str, body: SlotUpdateIn, user: User = Depends(require_csrf),
                db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    slot = _require_slot(db, user, slot_id)
    _check_version(slot, body.version)
    if body.basemap is not None:
        if body.basemap not in ALLOWED_BASEMAPS:
            raise HTTPException(422, f"basemap must be one of {sorted(ALLOWED_BASEMAPS)}")
        slot.basemap = body.basemap
    if body.name is not None:
        slot.name = _sanitize_text(body.name) or slot.name
    if body.description is not None:
        slot.description = _sanitize_text(body.description)
    if body.config is not None:
        slot.config = _validate_config(body.config, settings)
    slot.version += 1
    repo.record_audit(db, "mapslot.update", actor_id=user.id, resource_type="map_slot",
                      resource_id=slot.id, correlation_id=correlation_id())
    return _slot_dto(slot)


@router.post("/{slot_id}/rename")
def rename_slot(slot_id: str, body: RenameIn, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    slot = _require_slot(db, user, slot_id)
    _check_version(slot, body.version)
    slot.name = _sanitize_text(body.name) or slot.name
    slot.version += 1
    return _slot_dto(slot)


@router.post("/{slot_id}/reset")
def reset_slot(slot_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    slot = _require_slot(db, user, slot_id)
    default = next((d for d in repo.DEFAULT_SLOTS if d[0] == slot.slot_number), (slot.slot_number, slot.name, "standard"))
    slot.name, slot.basemap, slot.config = default[1], default[2], {}
    slot.version += 1
    repo.record_audit(db, "mapslot.reset", actor_id=user.id, resource_type="map_slot", resource_id=slot.id)
    return _slot_dto(slot)


@router.post("/{slot_id}/activate")
def activate_slot(slot_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    if not repo.set_active_slot(db, user.id, slot_id):
        raise HTTPException(404, "map slot not found")
    return {"ok": True, "active": slot_id}


@router.post("/{slot_id}/duplicate-to/{target_id}")
def duplicate_slot(slot_id: str, target_id: str, user: User = Depends(require_csrf), db: Session = Depends(get_db)):
    src = _require_slot(db, user, slot_id)
    dst = _require_slot(db, user, target_id)
    # Copy settings between existing slots — never exceeds the 3-slot limit.
    dst.basemap, dst.config = src.basemap, dict(src.config)
    dst.version += 1
    return _slot_dto(dst)


@router.get("/{slot_id}/export")
def export_slot(slot_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    slot = _require_slot(db, user, slot_id)
    return {"spec_version": 1, "kind": "map_slot", "basemap": slot.basemap, "config": slot.config}


@router.post("/import")
def import_slot(body: ImportIn, user: User = Depends(require_csrf), db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)):
    try:
        data = json.loads(body.config_json)
    except (ValueError, TypeError):
        raise HTTPException(422, "config_json is not valid JSON")
    if not isinstance(data, dict) or data.get("kind") != "map_slot":
        raise HTTPException(422, "not a map_slot export")
    basemap = data.get("basemap", "standard")
    if basemap not in ALLOWED_BASEMAPS:
        raise HTTPException(422, "invalid basemap in import")
    slot = next((s for s in repo.list_map_slots(db, user.id) if s.slot_number == body.slot_number), None)
    if not slot:
        raise HTTPException(404, "target slot not found")
    slot.basemap = basemap
    slot.config = _validate_config(data.get("config", {}), settings)
    slot.version += 1
    repo.record_audit(db, "mapslot.import", actor_id=user.id, resource_type="map_slot", resource_id=slot.id)
    return _slot_dto(slot)
