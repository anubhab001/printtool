from printtool.core.settings import DEFAULTS, ensure_settings_file, load_defaults, save_defaults, default_print_settings


def test_load_defaults_missing_file(tmp_path):
    path = tmp_path / "settings.yaml"
    assert load_defaults(path) == DEFAULTS


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "settings.yaml"
    save_defaults({"buffer_copy": True, "delete_after_print": True}, path)
    loaded = load_defaults(path)
    assert loaded["buffer_copy"] is True
    assert loaded["delete_after_print"] is True
    assert loaded["fit_to_page"] is True  # unspecified keys keep their default


def test_default_print_settings_reflects_saved_values(tmp_path):
    path = tmp_path / "settings.yaml"
    save_defaults({"buffer_copy": True}, path)
    settings = default_print_settings(path)
    assert settings.buffer_copy is True
    assert settings.delete_after_print is False


def test_ensure_settings_file_writes_a_real_file_on_first_run(tmp_path):
    path = tmp_path / "settings.yaml"
    assert not path.is_file()
    returned = ensure_settings_file(path)
    assert returned == path
    assert path.is_file()
    assert load_defaults(path) == DEFAULTS


def test_ensure_settings_file_does_not_overwrite_existing(tmp_path):
    path = tmp_path / "settings.yaml"
    save_defaults({"buffer_copy": True}, path)
    ensure_settings_file(path)
    assert load_defaults(path)["buffer_copy"] is True
