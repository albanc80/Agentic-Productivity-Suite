"""Readable copies of chats and deliverables in the outputs folder (Documents/Agentic-Suite-Outputs)."""

from pathlib import Path

from app.outputs import FOLDER_NAME, Outputs, documents_dir
from tests.conftest import OUTPUTS_FIXTURE, run_to_rest


def chat(cid="chat_abc123456", title="Plan the launch", dc="internal", messages=None):
    return {"id": cid, "agent_id": "program-manager", "data_class": dc, "title": title, "created_at": "2026-11-05T10:00:00Z",
            "updated_at": "2026-11-05T10:05:00Z", "messages": messages if messages is not None else [
                {"role": "user", "content": "What are the risks?", "files": [{"id": "file_1", "name": "plan.md"}], "at": "2026-11-05T10:00:00Z"},
                {"role": "assistant", "agent": "program-manager", "content": "## Risks\n\n- Vendor delay", "model": "local/m",
                 "at": "2026-11-05T10:00:05Z"}]}


def names(aid):
    return {"program-manager": "Program Manager"}.get(aid, aid)


def test_folder_tree_and_readme(tmp_path):
    out = Outputs(tmp_path / FOLDER_NAME)
    assert out.ensure() is None
    assert {p.name for p in (tmp_path / FOLDER_NAME).iterdir()} == {"Chats", "Runs", "Files", "README.md"}
    assert Outputs(None).ensure() is None  # feature off: nothing to do
    blocked = tmp_path / "a-file"
    blocked.write_text("x")
    assert "could not be created" in Outputs(blocked / "sub").ensure()  # unwritable: a readable warning, no crash


def test_chat_transcript_follows_the_chat(tmp_path):
    out = Outputs(tmp_path)
    out.ensure()
    p = out.save_chat(chat(title="New chat"), names)
    assert p.name == "2026-11-05-new-chat-bc123456.md"  # last 8 letters and digits of the id keep names unique
    p = out.save_chat(chat(), names)  # the title changed after the first message: one file, renamed
    files = list((tmp_path / "Chats").iterdir())
    assert files == [p] and p.name == "2026-11-05-plan-the-launch-bc123456.md"
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# Plan the launch") and "Agent: Program Manager" in text
    assert "**You** · 2026-11-05 10:00" in text and "Attached: plan.md" in text
    assert "**Program Manager** · 2026-11-05 10:00 · local/m" in text and "- Vendor delay" in text
    out.delete_chat("chat_abc123456")
    assert not list((tmp_path / "Chats").iterdir())


def test_restricted_work_never_leaves_the_app(tmp_path):
    out = Outputs(tmp_path)
    out.ensure()
    out.save_chat(chat(), names)
    assert out.save_chat(chat(dc="restricted"), names) is None
    assert not list((tmp_path / "Chats").iterdir())  # switching a chat to restricted removes its copy too
    assert out.save_run({"id": "run_x", "title": "T", "data_class": "restricted", "deliverable": "# T"}) is None
    assert out.save_file(chat(dc="restricted"), "t.md", "md", "# T") is None
    assert not list((tmp_path / "Runs").iterdir()) and not list((tmp_path / "Files").iterdir())


def test_runs_and_requested_files(tmp_path):
    out = Outputs(tmp_path)
    out.ensure()
    md = out.save_run({"id": "run_0001aaaa", "title": "Decision brief: build vs buy", "data_class": "internal",
                       "created_at": "2026-11-05T09:00:00Z", "deliverable": "# Decision\n\n| A | B |\n|---|---|\n| 1 | 2 |"})
    assert md.name == "2026-11-05-decision-brief-build-vs-buy-run0001a.md".replace("run0001a", "0001aaaa")
    html = md.with_suffix(".html").read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and "<table>" in html
    assert out.save_run({"id": "run_2", "title": "x", "data_class": "internal", "deliverable": ""}) is None
    a = out.save_file(chat(), "q4.html", "html", "# Q4\n\nOne")
    b = out.save_file(chat(), "q4.html", "html", "# Q4\n\nTwo")  # a different file of the same name is kept
    c = out.save_file(chat(), "q4.html", "html", "# Q4\n\nTwo")  # the same content is not duplicated
    assert a.name == "q4.html" and b.name == "q4-2.html" and c == b
    assert "<script" not in out.save_file(chat(), "x.html", "html", "<script>alert(1)</script>").read_text(encoding="utf-8")


def test_documents_folder_follows_linux_user_dirs(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "user-dirs.dirs").write_text('XDG_DOCUMENTS_DIR="$HOME/Dokumente"\n', encoding="utf-8")
    assert documents_dir() == Path.home() / "Dokumente"
    (tmp_path / "user-dirs.dirs").write_text("# nothing here\n", encoding="utf-8")
    assert documents_dir() == Path.home() / "Documents"


def test_settings_default_and_off(tmp_path, monkeypatch):
    from app.settings import load_settings
    from tests.conftest import ROOT
    monkeypatch.setenv("SUITE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SUITE_OUTPUTS_DIR", "off")
    assert load_settings(ROOT, ROOT / "config" / "suite.example.yaml").outputs_dir is None
    monkeypatch.delenv("SUITE_OUTPUTS_DIR")
    assert load_settings(ROOT, ROOT / "config" / "suite.example.yaml").outputs_dir == documents_dir() / FOLDER_NAME


async def test_finished_runs_are_copied(make_engine, tmp_path):
    from tests.conftest import contract
    eng, *_ = make_engine(cloud_script=lambda *a: "# Daily answer\n\nDo the thing.\n\n" + contract())
    eng.outputs = Outputs(tmp_path)
    eng.outputs.ensure()
    rid = await eng.start("quick-ask", {"request": "What should I focus on?"})
    await run_to_rest(eng, rid)
    [md] = list((tmp_path / "Runs").glob("*.md"))
    assert "Do the thing." in md.read_text(encoding="utf-8") and md.with_suffix(".html").exists()


def test_tests_use_a_throwaway_outputs_folder():
    assert OUTPUTS_FIXTURE.name.startswith("suite-outputs-") and "Documents" not in str(OUTPUTS_FIXTURE)
