from pi.local_agent_node.agent import LocalAgentNode


def test_executes_two_task_types(tmp_path):
    agent = LocalAgentNode("http://example.com", "node-1", str(tmp_path / "agent.db"), mock_mode=True)

    r1 = agent.execute_task({"id": "1", "type": "data_validation", "payload": {"record": {"a": 1}}})
    r2 = agent.execute_task({"id": "2", "type": "file_processing", "payload": {"text": "hello"}})

    assert r1.success and r1.proof["valid"] is True
    assert r2.success and len(r2.proof["sha256"]) == 64

    stats = agent.stats()
    assert stats["tasks_completed"] == 2
    assert stats["watt_earned"] >= 2
