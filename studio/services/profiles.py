from __future__ import annotations

import json

from studio.config import Settings
from studio.schemas import CharacterProfileSummary


class CharacterProfileStore:
    """Loads validated, user-facing character conditioning presets."""

    def __init__(self, settings: Settings) -> None:
        raw = json.loads(settings.character_profiles_path.read_text(encoding="utf-8"))
        profiles = [
            CharacterProfileSummary.model_validate(item) for item in raw.get("profiles", [])
        ]
        self._profiles = {profile.id: profile for profile in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("Character profile ids must be unique")

    def list_profiles(self) -> list[CharacterProfileSummary]:
        return list(self._profiles.values())

    def get(self, profile_id: str) -> CharacterProfileSummary:
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise ValueError(f"Unknown character_profile_id: {profile_id}") from exc
