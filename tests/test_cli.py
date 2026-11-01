import json

from satnogs_verify.cli import main


def test_cli_writes_markdown_and_json(good_source, fix, tmp_path, capsys):
    out = tmp_path / "r.json"
    code = main(["100001", "--log", str(fix / "client_good.log"), "--probe", str(fix / "probe_ok.log"),
                 "--baseline", "baseline.example.json", "--json", str(out)], source=good_source)
    text = capsys.readouterr().out
    assert code == 0
    assert "verdict: **PASS**" in text and "| 4 | Client start offset | PASS |" in text
    assert json.loads(out.read_text())["verdict"] == "PASS"
