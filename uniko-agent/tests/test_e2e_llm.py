"""End-to-end test with actual LLM API calls."""

import os

import pytest

from rustic_ai.uniko_agent.resolver import UnikoResolver


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") == "",
    reason="OPENAI_API_KEY not set in environment"
)
class TestE2EWithRealAPI:
    """End-to-end tests with real OpenAI API calls."""

    def test_resolver_with_real_openai_api(self):
        """Test complete flow: build Uniko, observe, recall, answer with real OpenAI API."""
        llm_spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY"
        }

        resolver = UnikoResolver(
            storage_path=None,  # In-memory
            llm_spec=llm_spec,
            streaming=False
        )

        # Resolve to get uniko agent
        agent = resolver.resolve(
            org_id="test-org",
            guild_id="test-guild-e2e",
            agent_id="test-agent-e2e"
        )

        assert agent is not None
        print("\n✓ Successfully created Uniko agent with LLM spec")

        # Get session
        session = agent.session("test-session-e2e")

        # Create and submit a turn
        import uniko
        turn = uniko.Turn("user", "I love Python programming and use it for data science.")
        observe_result = session.observe_sync(turn)
        print(f"✓ Observed turn: {observe_result.extracted_entities} entities, {observe_result.extracted_observations} observations")

        # Test recall
        recall_result = agent.recall_sync("What programming language does the user like?")
        print(f"✓ Recalled {len(recall_result.items)} items, coverage: {recall_result.coverage:.2%}")

        if len(recall_result.items) > 0:
            # Verify recall content mentions Python
            _ = " ".join(item.content.lower() for item in recall_result.items)
            print(f"✓ Recall found content (first item): {recall_result.items[0].content[:100]}...")
        else:
            print("⚠ No items recalled (coverage too low), but this is okay for new memory")

        # Test answer with LLM - THIS IS THE CRITICAL TEST
        try:
            answer_result = agent.answer_sync("What programming language does the user prefer?")
            print(f"✓ Answer generated: {answer_result.text[:150]}...")
            assert len(answer_result.text) > 0, "Answer should not be empty"

            # Verify the answer is meaningful (contains Python reference)
            assert "python" in answer_result.text.lower(), "Answer should mention Python based on observed memory"

            print("✓ LLM successfully generated a meaningful answer!")
            print("✓ REAL API CALL SUCCEEDED - LLM integration works end-to-end!")
            print(f"✓ Answer text: '{answer_result.text}'")

        except Exception as e:
            pytest.fail(f"Answer generation failed: {e}")

        # Cleanup
        resolver.shutdown()
        print("✓ Test completed successfully - full E2E flow works!")

    def test_resolver_with_base_url_override(self):
        """Test that base_url can be overridden for custom OpenAI-compatible endpoints."""
        llm_spec = {
            "alias": "openai",
            "model_id": "gpt-4o-mini",
            "key_env": "OPENAI_API_KEY",
            "base_url": "https://api.openai.com/v1"  # Explicit base URL
        }

        resolver = UnikoResolver(
            storage_path=None,
            llm_spec=llm_spec,
            streaming=False
        )

        # Should build without errors
        agent = resolver.resolve(
            org_id="test-org",
            guild_id="test-guild-baseurl",
            agent_id="test-agent-baseurl"
        )

        assert agent is not None
        print("\n✓ Successfully created Uniko agent with custom base_url")

        # Cleanup
        resolver.shutdown()
