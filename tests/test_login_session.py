"""Unit tests for the pure login-session helpers (spiders/browser/login_session.py):
file naming, staleness, and login-form detection. `capture_login_session` is
deliberately excluded - it blocks on real stdin input against a real headed
browser, not something an automated suite can drive.
"""
import os
import tempfile
import time

from spiders.browser.login_session import has_login_form, is_session_valid, session_path


def test_session_path_scopes_the_file_by_site():
    assert session_path("example.com") == os.path.join("data/sessions", "example.com.json")
    assert session_path("example.com", sessions_dir="/tmp/sessions") == "/tmp/sessions/example.com.json"


def test_is_session_valid_false_when_file_is_missing():
    assert not is_session_valid("/tmp/definitely-not-a-real-session-file.json", max_age_hours=24.0)


def test_is_session_valid_true_within_the_age_window():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        assert is_session_valid(path, max_age_hours=24.0)
    finally:
        os.remove(path)


def test_is_session_valid_false_once_past_the_age_window():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    try:
        stale = time.time() - (25 * 3600)
        os.utime(path, (stale, stale))
        assert not is_session_valid(path, max_age_hours=24.0)
    finally:
        os.remove(path)


def test_has_login_form_true_for_a_password_input():
    components = [
        {"tag": "input", "input_type": "text"},
        {"tag": "input", "input_type": "password"},
    ]
    assert has_login_form(components)


def test_has_login_form_false_with_no_password_input():
    components = [
        {"tag": "input", "input_type": "text"},
        {"tag": "button"},
    ]
    assert not has_login_form(components)


def test_has_login_form_false_for_an_empty_page():
    assert not has_login_form([])
