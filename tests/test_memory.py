from app.memory.store import LongTermMemory, ShortTermMemory


def test_short_term_memory_conversation_tracking():
    stm = ShortTermMemory()
    stm.add_turn("user", "hello")
    stm.add_turn("assistant", "hi there")
    assert stm.recent(1) == [{"role": "assistant", "content": "hi there"}]
    stm.clear()
    assert stm.conversation == []


def test_long_term_memory_remember_and_recall(tmp_path):
    ltm = LongTermMemory(path=tmp_path / "memory.json")
    ltm.remember("favorite_project", "F1 Race Engine")
    assert ltm.recall("favorite_project") == "F1 Race Engine"
    assert ltm.forget("favorite_project") is True
    assert ltm.recall("favorite_project") is None


def test_long_term_memory_projects(tmp_path):
    ltm = LongTermMemory(path=tmp_path / "memory.json")
    ltm.set_project("F1 project", "/home/user/projects/f1")
    assert ltm.get_project("f1 project") == "/home/user/projects/f1"
