from studio.config import Settings
from studio.services.profiles import CharacterProfileStore


def test_character_profiles_are_loaded_from_configuration() -> None:
    store = CharacterProfileStore(Settings.from_environment())

    profile = store.get("hotarugusa")

    assert profile.name == "蛍草（陰陽師・原作寄せ）"
    assert profile.lora_scale == 0.85
    assert "light blue bob cut" in profile.prompt
    assert "large dark navy hair bow" in profile.prompt
