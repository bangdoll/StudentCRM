from pathlib import Path

from data_gateway import StudentDataGateway


def test_relative_checkout_path_reads_bundled_students(monkeypatch):
    app_dir = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(app_dir)
    relative = StudentDataGateway(".")
    absolute = StudentDataGateway(str(app_dir))
    assert relative.load_students() == absolute.load_students()
    assert len(relative.load_students()) >= 64


def test_explicit_app_directory_keeps_writes_inside_it(tmp_path):
    (tmp_path / "data").mkdir()
    gateway = StudentDataGateway(str(tmp_path))
    gateway.save_effectiveness_radar_data({"items": [], "summary": {"total_tracked": 0}})
    assert (tmp_path / "data" / "effectiveness_radar.json").is_file()
    assert Path(gateway.app_dir) == tmp_path
