import pytest


@pytest.mark.regression
class TestStartup:
    def test_terminal_imports(self):
        import terminal

        assert terminal

    def test_server_imports(self):
        import server

        assert server

    def test_brain_initializes(self, api):
        r = api.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "online"
