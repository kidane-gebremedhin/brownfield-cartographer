"""Tests for token budget."""
from llm.budget import TokenBudget

def test_budget_add_remaining():
    b = TokenBudget(limit_input=1000, limit_output=500)
    assert b.remaining_input == 1000
    b.add(100, 50)
    assert b.spent_input == 100
    assert b.remaining_input == 900

def test_budget_can_afford():
    b = TokenBudget(limit_input=100, limit_output=50)
    assert b.can_afford(50, 25) is True
    b.add(50, 25)
    assert b.can_afford(51, 0) is False

def test_budget_reset():
    b = TokenBudget(limit_input=100, limit_output=100)
    b.add(10, 20)
    b.reset()
    assert b.spent_input == 0
