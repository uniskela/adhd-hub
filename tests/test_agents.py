from __future__ import annotations

import json
import tomllib

import httpx
import pytest

from adhd_hub import connect


def run_cli(argv):
    from adhd_hub.cli import main

    with pytest.raises(SystemExit) as raised:
        main(argv)
    return raised.value.code


@pytest.fixture
def agent_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("ADHD_HUB_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ADHD_HUB_CREDENTIALS", str(home / "credentials.json"))
    return home


def test_claude_documented_user_config_and_interpolation(agent_home):
    path = connect.claude_user_mcp_path()
    assert path == agent_home / ".claude.json"
    path.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    connect.merge_claude_mcp(path, "https://hub.example")
    data = json.loads(path.read_text())
    assert data["theme"] == "dark"
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["adhd-hub"]["headers"] == {
        "Authorization": "Bearer ${ADHD_HUB_AUTH_TOKEN}"
    }
    assert connect.merge_claude_mcp(path, "https://hub.example") == "unchanged"


@pytest.mark.parametrize("agent", ["claude", "cursor", "codex"])
def test_custom_auth_is_never_overwritten(agent_home, agent):
    path = agent_home / ("config.toml" if agent == "codex" else "mcp.json")
    if agent == "codex":
        original = '[mcp_servers.adhd-hub]\nurl = "https://hub.example/mcp"\nbearer_token_env_var = "CUSTOM_TOKEN"\n'
    else:
        original = json.dumps(
            {
                "mcpServers": {
                    "adhd-hub": {
                        "url": "https://hub.example/mcp",
                        "headers": {"Authorization": "Bearer custom-secret"},
                    }
                }
            }
        )
    path.write_text(original)
    with pytest.raises(ValueError, match="custom"):
        getattr(connect, f"merge_{agent}_mcp")(path, "https://other.example")
    assert path.read_text() == original


def test_codex_preserves_options_and_quoted_table(agent_home):
    path = agent_home / "config.toml"
    path.write_text(
        '# keep\nmodel = "test"\n[mcp_servers."adhd-hub"]\n'
        'url = "https://old.example/mcp"\n'
        'bearer_token_env_var = "ADHD_HUB_AUTH_TOKEN"\n'
        'startup_timeout_sec = 45\n[mcp_servers.other]\ncommand = "other"\n'
    )
    connect.merge_codex_mcp(path, "https://new.example")
    data = tomllib.loads(path.read_text())
    assert data["mcp_servers"]["adhd-hub"]["startup_timeout_sec"] == 45
    assert data["mcp_servers"]["adhd-hub"]["url"] == "https://new.example/mcp"
    assert data["mcp_servers"]["other"] == {"command": "other"}
    assert "# keep" in path.read_text()
    assert connect.merge_codex_mcp(path, "https://new.example") == "unchanged"


def test_setup_scope_conflict_preview_and_repair(agent_home, tmp_path):
    from adhd_hub.agents import setup_agents

    project = tmp_path / "project"
    project.mkdir()
    user = connect.cursor_user_mcp_path()
    connect.merge_cursor_mcp(user, "https://hub.example")
    result = setup_agents(
        hub_url="https://hub.example",
        agents=["cursor"],
        scope="project",
        project=project,
        dry_run=True,
    )
    assert not result.ok
    assert any("conflict" in s.detail for s in result.steps)
    assert not (project / ".cursor").exists()
    user.unlink()
    result = setup_agents(
        hub_url="https://hub.example",
        agents=["cursor"],
        scope="project",
        project=project,
        dry_run=True,
    )
    assert result.ok
    assert not (project / ".cursor").exists()
    for _ in range(2):
        result = setup_agents(
            hub_url="https://hub.example", agents=["cursor"], scope="project", project=project
        )
        assert result.ok
    assert json.loads((project / ".cursor/mcp.json").read_text())["mcpServers"]["adhd-hub"]


def test_noninteractive_requires_selection_without_login(agent_home, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert run_cli(["agents", "setup", "--non-interactive", "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert "--agents" in str(result)
    assert not connect.claude_user_mcp_path().exists()


def test_user_setup_needs_no_checkout_and_reports_missing_runtime(agent_home, monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.chdir(agent_home)
    assert (
        run_cli(
            [
                "agents",
                "setup",
                "--agents",
                "codex,claude,cursor",
                "--hub",
                "https://hub.example",
                "--non-interactive",
                "--json",
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert "MISSING" in str(result)
    assert "not installed" in str(result)
    assert not (agent_home / "AGENTS.md").exists()
    assert connect.claude_user_mcp_path().exists()
    assert tomllib.loads(connect.codex_config_path().read_text())["mcp_servers"]["adhd-hub"]


def test_mcp_probe_json_and_sse():
    from adhd_hub.mcp_probe import probe_mcp

    for sse in (False, True):
        methods = []

        def handle(request, methods=methods, sse=sse):
            payload = json.loads(request.content)
            methods.append(payload["method"])
            assert request.headers["Authorization"] == "Bearer test-secret"
            if payload["method"] == "initialize":
                result = {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test", "version": "1"},
                }
            else:
                assert request.headers["Mcp-Session-Id"] == "session"
                assert request.headers["MCP-Protocol-Version"] == "2025-03-26"
                if payload["method"] == "notifications/initialized":
                    return httpx.Response(202)
                result = {"tools": [{"name": "get_overview"}]}
            body = {"jsonrpc": "2.0", "id": payload["id"], "result": result}
            if sse:
                content = ': ping\n\ndata: {"jsonrpc":"2.0","method":"notifications/test"}\n\n'
                content += "event: message\ndata: " + json.dumps(body) + "\n\n"
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream", "mcp-session-id": "session"},
                    text=content,
                )
            return httpx.Response(200, headers={"mcp-session-id": "session"}, json=body)

        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            result = probe_mcp("https://hub.example/mcp", token="test-secret", client=client)
        assert result["tools_discovered"]
        assert result["authentication"] == "successful"
        assert methods == ["initialize", "notifications/initialized", "tools/list"]


@pytest.mark.parametrize("status", [401, 403, 500])
def test_mcp_probe_redacts_rejected_credentials(status):
    from adhd_hub.mcp_probe import probe_mcp

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, text="test-secret expired credential")
        )
    ) as client:
        result = probe_mcp("https://hub.example/mcp", token="test-secret", client=client)
    assert not result["tools_discovered"]
    assert result["http_status"] == status
    assert "test-secret" not in json.dumps(result)


def test_doctor_does_not_use_cli_session_as_agent_credentials(agent_home, monkeypatch):
    from adhd_hub.agents import diagnose_agents
    from adhd_hub.connect_login import save_credentials

    save_credentials("http://127.0.0.1:9", "ahcli_private-session")
    connect.merge_claude_mcp(connect.claude_user_mcp_path(), "http://127.0.0.1:9")
    monkeypatch.setattr("shutil.which", lambda _: "/test/claude")
    report = diagnose_agents(hub_url="http://127.0.0.1:9", agents=["claude"], scope="user")
    assert report.agent_status[0]["credentials"] == "MISSING"
    assert report.agent_status[0]["runtime_verification"] == "not available"
    assert "ahcli_private-session" not in json.dumps(report.agent_status)


@pytest.mark.parametrize("agent", ["claude", "cursor", "codex"])
def test_doctor_does_not_probe_client_oauth(agent_home, monkeypatch, agent):
    from unittest.mock import Mock

    from adhd_hub.agents import diagnose_agents

    path = (
        connect.codex_config_path()
        if agent == "codex"
        else getattr(connect, f"{agent}_user_mcp_path")()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if agent == "codex":
        path.write_text('[mcp_servers.adhd-hub]\nurl = "https://hub.example/mcp"\n')
    else:
        path.write_text(
            json.dumps({"mcpServers": {"adhd-hub": {"url": "https://hub.example/mcp"}}})
        )
    monkeypatch.setenv("ADHD_HUB_AUTH_TOKEN", "unrelated-shell-credential")
    probe = Mock(return_value={"tools_discovered": True, "detail": "anonymous tools available"})
    monkeypatch.setattr("adhd_hub.agents.probe_mcp", probe)

    report = diagnose_agents(hub_url="https://hub.example", agents=[agent])

    probe.assert_not_called()
    row = report.agent_status[0]
    assert row["state"] == "configured"
    assert row["runtime_verification"] == "not available"
    assert "mcp" not in row
    assert any(
        "client OAuth" in step.detail and "not available" in step.detail for step in report.steps
    )


@pytest.mark.parametrize(
    "agents", ["claude-code", "claude-code,claude", "claude,claude-code", "claude,claude"]
)
def test_legacy_doctor_accepts_claude_code_alias(agent_home, monkeypatch, capsys, agents):
    hub = "http://127.0.0.1:8787"
    connect.claude_user_mcp_path().write_text(
        json.dumps({"mcpServers": {"adhd-hub": {"url": hub + "/mcp"}}})
    )
    monkeypatch.setattr(connect, "probe_hub", lambda *a, **k: (True, "health OK"))
    monkeypatch.delenv("ADHD_HUB_PUBLIC_URL", raising=False)

    assert run_cli(["doctor", "--agents", agents, "--hub", hub, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["agents"]) == 1
    assert result["agents"][0]["agent"] == "claude"
    assert result["agents"][0]["configured"]


@pytest.mark.parametrize("agent", ["claude", "cursor", "codex"])
@pytest.mark.parametrize("probe", [False, True])
def test_doctor_warns_without_probing_local_stdio(agent_home, monkeypatch, agent, probe):
    from unittest.mock import Mock

    from adhd_hub.agents import config_paths, diagnose_agents

    path = config_paths(agent, None)[0][1]
    path.parent.mkdir(parents=True, exist_ok=True)
    if agent == "codex":
        path.write_text('[mcp_servers.adhd-hub]\ncommand = "adhd-hub"\nargs = ["mcp-stdio"]\n')
    else:
        entry = {"command": "adhd-hub", "args": ["mcp-stdio"]}
        path.write_text(json.dumps({"mcpServers": {"adhd-hub": entry}}))
    original = path.read_bytes()
    http_probe = Mock()
    monkeypatch.setattr("adhd_hub.agents.probe_mcp", http_probe)

    report = diagnose_agents(hub_url="https://hub.example", agents=[agent], probe=probe)

    assert report.ok
    row = report.agent_status[0]
    assert row["state"] == "configured"
    assert row["runtime_verification"] == "not available"
    assert "mcp" not in row
    assert any(step.status == "warn" and "local stdio" in step.detail for step in report.steps)
    http_probe.assert_not_called()
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "host", ["localhost", "127.0.0.1", "127.0.0.2", "127.255.255.254", "[::1]"]
)
def test_mcp_url_accepts_http_loopback(host):
    from adhd_hub.mcp_probe import validate_mcp_url

    validate_mcp_url(f"http://{host}:8787/mcp")


@pytest.mark.parametrize(
    "host", ["127.example.com", "127.0.0.1.example.com", "192.168.1.2", "[::2]", "hub.example"]
)
def test_mcp_url_requires_https_for_non_loopback(host):
    from adhd_hub.mcp_probe import validate_mcp_url

    with pytest.raises(ValueError, match="HTTPS outside loopback"):
        validate_mcp_url(f"http://{host}:8787/mcp")
    validate_mcp_url(f"https://{host}:8787/mcp")


@pytest.mark.parametrize(
    "agent,wrong", [("claude", "${env:ADHD_HUB_AUTH_TOKEN}"), ("cursor", "${ADHD_HUB_AUTH_TOKEN}")]
)
def test_diagnostics_and_repair_interpolation(agent_home, agent, wrong):
    from adhd_hub.agents import config_paths, diagnose_agents, setup_agents

    path = dict(config_paths(agent, None))["user"]
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other": {"command": "keep"},
                    "adhd-hub": {
                        "url": "https://hub.example/mcp",
                        "headers": {"Authorization": "Bearer " + wrong},
                    },
                }
            }
        )
    )
    original = path.read_text()
    report = diagnose_agents(hub_url="https://hub.example", agents=[agent], probe=False)
    assert not report.ok
    report = setup_agents(hub_url="https://hub.example", agents=[agent], dry_run=True)
    assert report.ok and path.read_text() == original
    setup_agents(hub_url="https://hub.example", agents=[agent])
    assert path.with_name(path.name + ".adhd-hub.bak").read_text() == original
    assert (
        diagnose_agents(hub_url="https://hub.example", agents=[agent], probe=False).agent_status[0][
            "authentication_method"
        ]
        == "environment bearer"
    )
    assert json.loads(path.read_text())["mcpServers"]["other"] == {"command": "keep"}


def test_repair_cli_preview_is_idempotent(agent_home, capsys):
    args = ["agents", "repair", "--agents", "claude", "--hub", "https://hub.example", "--json"]
    assert run_cli(args) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"]
    assert not connect.claude_user_mcp_path().exists()
    assert run_cli([*args, "--apply"]) == 1  # Registration saved; credential still missing.
    capsys.readouterr()
    original = connect.claude_user_mcp_path().read_bytes()
    assert run_cli([*args, "--apply"]) == 1
    capsys.readouterr()
    assert connect.claude_user_mcp_path().read_bytes() == original


def test_scopes_and_service_environment_overrides(agent_home, tmp_path, monkeypatch):
    from adhd_hub.agents import diagnose_agents, setup_agents

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(agent_home / "custom-claude"))
    monkeypatch.setenv("CODEX_HOME", str(agent_home / "custom-codex"))
    assert connect.claude_user_mcp_path() == agent_home / "custom-claude/.claude.json"
    assert connect.codex_config_path() == agent_home / "custom-codex/config.toml"
    project = tmp_path / "service-workspace"
    project.mkdir()
    # cwd belongs to a different account; user setup must not read/write it.
    monkeypatch.chdir(project)
    setup_agents(hub_url="https://hub.example", agents=["claude"], scope="user")
    assert not (project / ".mcp.json").exists()
    assert not setup_agents(
        hub_url="https://hub.example", agents=["claude"], scope="project", project=project
    ).ok
    user = connect.claude_user_mcp_path()
    user.write_text(
        json.dumps(
            {
                "projects": {
                    str(project): {"mcpServers": {"adhd-hub": {"url": "https://old.example/mcp"}}}
                }
            }
        )
    )
    assert not setup_agents(hub_url="https://hub.example", agents=["claude"], project=project).ok
    row = diagnose_agents(
        hub_url="https://hub.example", agents=["claude"], project=project, probe=False
    ).agent_status[0]
    assert row["registrations"][0]["scope"] == "local"


@pytest.mark.parametrize(
    "failure", ["timeout", "transport", "rpc", "wrong_id", "no_tools", "redirect"]
)
def test_probe_failure_is_safe_and_never_follows_external_redirect(failure):
    from adhd_hub.mcp_probe import probe_mcp

    requests = []

    def handle(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test-secret")
        if failure == "transport":
            raise httpx.ConnectError("test-secret")
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://other.example/mcp"})
        if failure == "rpc":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": 1, "error": {"message": "test-secret"}}
            )
        if failure == "wrong_id":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 9, "result": {}})
        payload = json.loads(request.content)
        if "id" not in payload:
            return httpx.Response(202)
        result = {"protocolVersion": "2025-03-26", "serverInfo": {}, "capabilities": {}}
        if payload["method"] == "tools/list":
            result = {"tools": [{"name": "unrelated"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = probe_mcp("https://hub.example/mcp", token="test-secret", client=client)
    assert not result["tools_discovered"]
    assert "test-secret" not in json.dumps(result)
    assert all(r.url.host == "hub.example" for r in requests)


def test_probe_refuses_plaintext_credentials():
    from adhd_hub.mcp_probe import probe_mcp

    def unexpected_request(request):
        pytest.fail("credentials must not be sent")

    with httpx.Client(transport=httpx.MockTransport(unexpected_request)) as client:
        assert not probe_mcp("http://remote.example/mcp", token="secret", client=client)[
            "initialized"
        ]


def test_probe_local_streaming_server_session_and_pagination():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from adhd_hub.mcp_probe import probe_mcp

    received = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((request, dict(self.headers)))
            method = request["method"]
            if method == "notifications/initialized":
                self.send_response(202)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if method == "initialize":
                result = {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {},
                }
            elif request.get("params", {}).get("cursor") == "page2":
                result = {"tools": [{"name": "get_overview"}]}
            else:
                result = {"tools": [{"name": "resolve_project"}], "nextCursor": "page2"}
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Mcp-Session-Id", "local-session")
            self.end_headers()
            # Deliberately keep the SSE connection open: read-all would hang.
            self.wfile.write(
                (
                    "data: "
                    + json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result})
                    + "\n\n"
                ).encode()
            )
            self.wfile.flush()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = probe_mcp(
            f"http://127.0.0.1:{server.server_port}/mcp", token="test-only", timeout=2
        )
        assert result["tools_discovered"]
        assert result["tool_count"] == 2
        assert len(received) == 4
        assert all(headers.get("Mcp-Session-Id") == "local-session" for _, headers in received[1:])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_connect_missing_agent_credentials_is_failure(agent_home, monkeypatch):
    monkeypatch.setattr(connect, "probe_hub", lambda *a, **k: (True, "health OK"))
    report = connect.run_connect(
        project=agent_home,
        hub_url="http://127.0.0.1:9",
        agents=["claude"],
        scope="user",
        install_skills_flag=False,
        skills_source="uniskela/adhd-hub",
        cursor_rule=False,
        openclaw_skills=False,
        register=False,
        find_roots=None,
        token="ahcli_test",
    )
    assert not report.ok
    assert connect.claude_user_mcp_path().exists()
    assert report.agent_status[0]["credentials"] == "MISSING"


def test_probe_sse_crlf_split_between_chunks():
    from adhd_hub.mcp_probe import probe_mcp

    class Stream(httpx.SyncByteStream):
        def __init__(self, body):
            self.body = body

        def __iter__(self):
            # A legal transport may split at any byte, including CR | LF.
            for byte in self.body:
                yield bytes([byte])

    def handle(request):
        payload = json.loads(request.content)
        if "id" not in payload:
            return httpx.Response(202)
        result = (
            {"protocolVersion": "2025-03-26", "serverInfo": {}}
            if payload["method"] == "initialize"
            else {"tools": [{"name": "get_overview"}]}
        )
        body = "data: " + json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": result})
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=Stream((body + "\r\n\r\n").encode()),
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        assert probe_mcp("https://hub.example/mcp", token="test", client=client)["tools_discovered"]


def test_interactive_selection_offers_detected_clients(monkeypatch, capsys):
    from adhd_hub.agents import select_agents

    monkeypatch.setattr("shutil.which", lambda name: "/bin/claude" if name == "claude" else None)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert select_agents("") == ["claude"]
    assert "claude" in capsys.readouterr().out


def test_json_never_echoes_malformed_config_or_token(agent_home, capsys):
    path = connect.claude_user_mcp_path()
    path.write_text('{"mcpServers":{"adhd-hub":{"headers":{"Authorization":"secret-value"}}} bad')
    assert run_cli(["agents", "doctor", "--agents", "claude", "--json"]) == 1
    output = capsys.readouterr().out
    assert "secret-value" not in output
    assert json.loads(output)["agents"][0]["state"] == "invalid or unreadable configuration"


def test_existing_auth_and_advanced_headers_are_preserved(agent_home):
    from adhd_hub.agents import diagnose_agents

    path = connect.cursor_user_mcp_path()
    path.parent.mkdir()
    entry = {
        "url": "https://hub.example/mcp",
        "headers": {"Authorization": "Bearer ${env:ADHD_HUB_AUTH_TOKEN}", "X-Custom": "private"},
    }
    path.write_text(json.dumps({"mcpServers": {"adhd-hub": entry}}))
    assert "unchanged" in connect.merge_cursor_mcp(path, "https://hub.example")
    row = diagnose_agents(
        hub_url="https://hub.example", agents=["cursor"], probe=False
    ).agent_status[0]
    assert row["authentication_method"] == "custom authentication (not probed)"
    assert json.loads(path.read_text())["mcpServers"]["adhd-hub"] == entry


def test_codex_ancestor_conflict_and_project_trust_context(agent_home, tmp_path):
    from adhd_hub.agents import setup_agents

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    child = repo / "child"
    child.mkdir()
    connect.merge_codex_mcp(repo / ".codex/config.toml", "https://hub.example")
    report = setup_agents(
        hub_url="https://hub.example", agents=["codex"], scope="project", project=child
    )
    assert not report.ok
    assert not (child / ".codex").exists()


def test_installer_noninteractive_flags_and_no_false_banner():
    shell = connect.render_install_sh("https://hub.example")
    powershell = connect.render_install_ps1("https://hub.example")
    assert "--non-interactive)" in shell
    assert "[switch]$NonInteractive" in powershell
    assert 'if ($NonInteractive) { $connectArgs += "--non-interactive" }' in powershell
    assert "CLI login does not authenticate coding agents" in shell
    assert "CLI login does not authenticate coding agents" in powershell


def test_legacy_sse_transport_is_never_silently_retargeted(agent_home):
    path = connect.claude_user_mcp_path()
    original = json.dumps(
        {
            "mcpServers": {
                "adhd-hub": {
                    "type": "sse",
                    "url": "https://hub.example/sse",
                    "headers": {"Authorization": "Bearer ${ADHD_HUB_AUTH_TOKEN}"},
                }
            }
        }
    )
    path.write_text(original)
    with pytest.raises(ValueError, match="custom"):
        connect.merge_claude_mcp(path, "https://other.example", dry_run=True)
    assert path.read_text() == original


def test_use_hub_reuses_existing_scope_without_creating_duplicates(
    agent_home, tmp_path, monkeypatch
):
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setattr(connect, "probe_hub", lambda *a, **k: (True, "health OK"))
    path = project / ".mcp.json"
    connect.merge_claude_mcp(path, "https://old.example")
    report = connect.run_use_hub(
        hub_url="https://new.example", project=project, agents=["claude"], scope="both"
    )
    assert report.ok
    assert not connect.claude_user_mcp_path().exists()
    assert (
        json.loads(path.read_text())["mcpServers"]["adhd-hub"]["url"] == "https://new.example/mcp"
    )
