"""End-to-end browser UI tests for the Tumoh IDE chat panel."""

from __future__ import annotations

from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8000"


def _switch_to_chat(page: Page) -> None:
    page.goto(BASE_URL, wait_until="domcontentloaded")
    page.wait_for_selector("#chat-panel")
    page.locator("#tab-chat").click()
    page.wait_for_selector("#chat-panel:not(.hidden)")
    page.wait_for_selector(".chat-message.system", timeout=15000)
    expect(page.get_by_text("Connected to chat")).to_be_visible()


def test_chat_tab_opens_and_connects(page: Page) -> None:
    _switch_to_chat(page)
    expect(page.locator("#chat-panel")).to_be_visible()
    expect(page.locator("#chat-log .chat-message.system")).to_contain_text(
        "Connected to chat"
    )


def test_send_text_message(page: Page) -> None:
    _switch_to_chat(page)
    page.locator("#chat-input").fill("Hello from UI")
    page.locator("#chat-send").click()

    expect(page.locator("#chat-input")).to_have_value("")
    expect(page.locator(".chat-message.user")).to_contain_text("Hello from UI")

    page.wait_for_selector(".chat-message.assistant", timeout=15000)
    expect(page.locator(".chat-message.assistant")).to_be_visible()


def test_photo_logo_preview_renders(page: Page) -> None:
    _switch_to_chat(page)
    page.locator("#chat-input").fill("create a logo for Tumoh")
    page.locator("#chat-send").click()

    preview = page.locator(".chat-message.assistant img.preview")
    preview.wait_for(timeout=15000)
    expect(preview).to_be_visible()


def test_audio_sound_preview_renders(page: Page) -> None:
    _switch_to_chat(page)
    page.locator("#chat-input").fill("record an audio clip")
    page.locator("#chat-send").click()

    player = page.locator(".chat-message.assistant audio")
    player.wait_for(timeout=15000)
    expect(player).to_be_visible()


def test_video_preview_renders(page: Page) -> None:
    _switch_to_chat(page)
    page.locator("#chat-input").fill("make an animation promo")
    page.locator("#chat-send").click()

    preview = page.locator(".chat-message.assistant .video-preview")
    preview.wait_for(timeout=15000)
    expect(preview).to_be_visible()


def test_attachment_buttons_no_exceptions(page: Page) -> None:
    _switch_to_chat(page)
    errors: list[str] = []
    page.on("pageerror", lambda err: errors.append(str(err)))

    page.locator("#chat-record").click()
    page.locator("#chat-image-btn").click()
    page.locator("#chat-pdf-btn").click()
    page.wait_for_timeout(500)

    assert not errors, f"JavaScript errors detected: {errors}"
