"""Token budget tracking for LLM calls.

Tracks input and output token usage against configurable limits.
Used to prefer cheaper models for bulk work and reserve expensive models for synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenBudget:
    """Tracks spent and limit for input and output tokens."""

    limit_input: int = 0
    limit_output: int = 0
    spent_input: int = field(default=0, repr=False)
    spent_output: int = field(default=0, repr=False)

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage."""
        self.spent_input += input_tokens
        self.spent_output += output_tokens

    def can_afford(self, input_tokens: int, output_tokens: int) -> bool:
        """Return True if remaining budget allows this call."""
        if self.limit_input > 0 and self.spent_input + input_tokens > self.limit_input:
            return False
        if self.limit_output > 0 and self.spent_output + output_tokens > self.limit_output:
            return False
        return True

    def reset(self) -> None:
        """Reset spent counts to zero."""
        self.spent_input = 0
        self.spent_output = 0

    @property
    def remaining_input(self) -> int:
        """Remaining input token budget; -1 means unbounded."""
        if self.limit_input <= 0:
            return -1
        return max(0, self.limit_input - self.spent_input)

    @property
    def remaining_output(self) -> int:
        """Remaining output token budget; -1 means unbounded."""
        if self.limit_output <= 0:
            return -1
        return max(0, self.limit_output - self.spent_output)
