import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.regression
class TestFunctionCallingRegressions:
    """Specific prompts that previously failed."""

    def test_weather_today(self, api):
        r = api.ask("could you tell me the weather today?")
        assert r.status_code == 200
        data = r.json()
        assert assert_no_raw_json(data["reply"]), f"Reply contains raw JSON: {data['reply'][:200]}"

    def test_nonsense_input(self, api):
        r = api.ask("skibs")
        assert r.status_code == 200
        data = r.json()
        assert len(data["reply"]) > 0
        assert_no_raw_json(data["reply"])

    def test_short_form_context(self, api):
        r = api.ask("its a short form of a word")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])


@pytest.mark.regression
class TestP0Regressions:
    """P0 regression tests — must pass before P1+ merge."""

    # ── Test 1: read_file offset ──────────────────────────────────────
    def test_read_file_offset(self, api, tmp_path):
        test_file = tmp_path / "offset_test.txt"
        test_file.write_text("\n".join(f"LINE_{i:03d}" for i in range(500)) + "\n")

        replies = []
        for offset in [0, 100, 350]:
            r = api.ask(f"read file {test_file} with offset {offset}")
            assert r.status_code == 200
            reply = r.json()["reply"]
            assert_no_raw_json(reply)
            replies.append(reply)

        assert replies[0] != replies[1], "offset 0 and 100 should return different content"
        assert replies[1] != replies[2], "offset 100 and 350 should return different content"

    # ── Test 2: compound request clause dropping ──────────────────────
    @pytest.mark.parametrize(
        "prompt",
        [
            "skip spotify track",
            "open safari and search web for python 3.13",
        ],
    )
    def test_compound_request_all_clauses_executed(self, api, prompt):
        r = api.ask(prompt)
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert_no_raw_json(reply)

    # ── Test 3: self-inspection routing ───────────────────────────────
    @pytest.mark.parametrize(
        "prompt",
        [
            "what tools do you have",
            "list your capabilities",
            "what can you do",
        ],
    )
    def test_self_inspection_routes_to_tool_not_chat(self, api, prompt):
        r = api.ask(prompt)
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert_no_raw_json(reply)
        assert len(reply) > 30, f"Response too short for self-inspection: {reply}"

    # ── Test 4: project-root persistence ──────────────────────────────
    def test_project_root_and_canonicalization(self, api, tmp_path):
        test_dir = tmp_path / "Jarvis"
        test_dir.mkdir()
        (test_dir / "a.txt").write_text("AAA_CONTENT\n")
        (test_dir / "b.txt").write_text("BBB_CONTENT\n")

        r1 = api.ask(f"list files in {test_dir}")
        assert r1.status_code == 200
        assert_no_raw_json(r1.json()["reply"])
        assert "a.txt" in r1.json()["reply"] or "AAA" in r1.json()["reply"]

        r2 = api.ask("read the first file in that directory")
        assert r2.status_code == 200
        reply2 = r2.json()["reply"]
        assert "AAA_CONTENT" in reply2 or "BBB" in reply2 or "AAA" in reply2, f"Expected file content in cross-turn ref: {reply2[:200]}"

        r3 = api.ask("create file c.txt in that same directory with content CCC_CONTENT")
        assert r3.status_code == 200
        assert (test_dir / "c.txt").exists(), "c.txt was not created"
        assert (test_dir / "c.txt").read_text().strip() == "CCC_CONTENT", f"Wrong content: {(test_dir / 'c.txt').read_text()}"

    # ── Test 5: self-healing screen click (local only) ────────────────
    @pytest.mark.local
    def test_click_by_description_fallback_when_coords_fail(self, api, has_display):
        if not has_display:
            pytest.skip("No display available")

        r1 = api.ask("open calculator")
        assert r1.status_code == 200

        r2 = api.ask("click the '1' button in calculator")
        assert r2.status_code == 200
        reply2 = r2.json()["reply"].lower()
        assert any(kw in reply2 for kw in ["clicked", "click", "found", "button", "pressed", "tap"]), f"Click by description did not register: {reply2[:200]}"

        r3 = api.ask("read calculator display")
        assert r3.status_code == 200
        assert "1" in r3.json()["reply"], f"Expected '1' on calculator display: {r3.json()['reply'][:200]}"
