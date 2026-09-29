from pathlib import Path

from app.domain import journal_tail

HEADER = "ид_события,ид_канала_данных,дата,время,тревожное,значение_датчика\n"


def test_tail_keeps_alarms_and_state_changes(tmp_path: Path) -> None:
    (tmp_path / "справочник_каналов_датчиков.csv").write_text(
        "ид_канала_данных,тип_инж_системы,тип_датчика,тег_инженерной_системы,название_датчика,ид_объект\n"
        "7,Насосы,Состояние насоса,1-1.1,Н1 ПК10,5963\n",
        encoding="utf-8",
    )
    (tmp_path / "ext-journal-2025.csv").write_text(
        HEADER + "1,7,2025-12-31,23:00:00,f,Неисправен\n", encoding="utf-8"
    )
    (tmp_path / "ext-journal-2026.csv").write_text(
        HEADER
        + "2,7,2026-06-30,20:00:00,f,Норма\n"
        + "3,8,2026-06-30,21:00:00,f,0.02\n"
        + "4,7,2026-06-30,22:00:00,f,Неисправен\n"
        + "5,9,2026-06-30,23:00:00,t,1.4\n"
        + "6,7,2026-06-29,10:00:00,t,Неисправен\n",
        encoding="utf-8",
    )

    result = journal_tail.recent(tmp_path, 6, 10, None, "Europe/Moscow")

    assert [item["event_id"] for item in result["items"]] == ["5", "4"]
    assert result["items"][1]["name"] == "Н1 ПК10"
    assert result["items"][1]["object_id"] == "5963"
    assert result["latest_at"].isoformat().startswith("2026-06-30T23:00:00")


def test_tail_is_empty_without_journal(tmp_path: Path) -> None:
    assert journal_tail.recent(tmp_path, 6, 10, None, "Europe/Moscow")["items"] == []
