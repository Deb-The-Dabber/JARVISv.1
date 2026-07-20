import concurrent.futures

import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.integration
class TestTTSFallback:
    """Test TTS chain: ElevenLabs → Edge-TTS → macOS say"""

    def test_tts_fallback_works(self, api):
        r = api.ask("hello, test tts")
        assert r.status_code == 200
        data = r.json()
        assert data["reply"]
        assert_no_raw_json(data["reply"])

    def test_concurrent_tts_survives(self, api):
        """Multiple rapid requests should not crash."""
        def ask(q):
            return api.ask(q)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futures = [ex.submit(ask, f"test message {i}") for i in range(3)]
            for f in futures:
                r = f.result()
                assert r.status_code == 200
                assert r.json()["reply"]
