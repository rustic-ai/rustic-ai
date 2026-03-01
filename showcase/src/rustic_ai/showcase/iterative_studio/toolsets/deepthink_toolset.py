"""Deepthink Toolset - Strategic reasoning tools.

This toolset provides tools for the Adaptive Deepthink mode, enabling
structured strategic reasoning, hypothesis generation, critique, and
solution selection.
"""

import json
from typing import List, Optional

from pydantic import BaseModel, Field

from rustic_ai.core.guild.agent_ext.depends.llm.tools_manager import ToolSpec
from rustic_ai.llm_agent.react.toolset import ReActToolset


class GenerateStrategiesParams(BaseModel):
    """Parameters for the GenerateStrategies tool."""

    problem: str = Field(
        description="The problem or task to generate strategies for"
    )
    num_strategies: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Number of strategies to generate (1-5)",
    )
    constraints: Optional[str] = Field(
        default=None,
        description="Any constraints or requirements to consider",
    )


class GenerateHypothesesParams(BaseModel):
    """Parameters for the GenerateHypotheses tool."""

    strategy: str = Field(
        description="The strategy to generate hypotheses for"
    )
    context: Optional[str] = Field(
        default=None,
        description="Additional context about the problem domain",
    )


class CritiqueSolutionParams(BaseModel):
    """Parameters for the CritiqueSolution tool."""

    solution: str = Field(
        description="The solution to critique"
    )
    criteria: Optional[List[str]] = Field(
        default=None,
        description="Specific criteria to evaluate against",
    )
    original_problem: Optional[str] = Field(
        default=None,
        description="The original problem statement for context",
    )


class RedTeamParams(BaseModel):
    """Parameters for the RedTeam tool."""

    solution: str = Field(
        description="The solution to red-team"
    )
    attack_vectors: Optional[List[str]] = Field(
        default=None,
        description="Specific attack vectors or failure modes to consider",
    )


class SelectBestSolutionParams(BaseModel):
    """Parameters for the SelectBestSolution tool."""

    solutions: List[str] = Field(
        description="List of candidate solutions to compare"
    )
    criteria: Optional[List[str]] = Field(
        default=None,
        description="Criteria for selection (e.g., simplicity, robustness, efficiency)",
    )
    problem: Optional[str] = Field(
        default=None,
        description="The original problem for context",
    )


class RecordReasoningParams(BaseModel):
    """Parameters for the RecordReasoning tool."""

    stage: str = Field(
        description="The reasoning stage (e.g., 'strategy', 'hypothesis', 'critique', 'refinement')"
    )
    content: str = Field(
        description="The reasoning content to record"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Additional metadata about the reasoning step",
    )


class DeepthinkToolset(ReActToolset):
    """
    A ReActToolset providing strategic reasoning tools for Adaptive Deepthink mode.

    This toolset enables structured problem-solving through:
    - Strategy generation: Generate multiple approaches to a problem
    - Hypothesis generation: Develop testable hypotheses for strategies
    - Solution critique: Evaluate solutions against criteria
    - Red-teaming: Adversarial testing of solutions
    - Best solution selection: Compare and select optimal solutions
    - Reasoning recording: Track the reasoning process

    The toolset maintains reasoning history internally to support iterative
    refinement and self-reflection.

    Example usage in guild spec:
        properties:
          toolset:
            kind: rustic_ai.showcase.iterative_studio.toolsets.deepthink_toolset.DeepthinkToolset
    """

    # Internal reasoning history (not serialized)
    _reasoning_history: List[dict] = []
    _strategies: List[dict] = []
    _hypotheses: List[dict] = []
    _critiques: List[dict] = []

    def get_toolspecs(self) -> List[ToolSpec]:
        """Return the list of tool specifications available in this toolset."""
        return [
            ToolSpec(
                name="GenerateStrategies",
                description=(
                    "Generate multiple high-level strategies to approach a problem. "
                    "Each strategy provides a distinct angle or methodology. "
                    "Use this at the beginning of complex problem-solving."
                ),
                parameter_class=GenerateStrategiesParams,
            ),
            ToolSpec(
                name="GenerateHypotheses",
                description=(
                    "Generate testable hypotheses for a given strategy. "
                    "Hypotheses are specific, actionable ideas that can be validated. "
                    "Use after selecting a strategy to explore."
                ),
                parameter_class=GenerateHypothesesParams,
            ),
            ToolSpec(
                name="CritiqueSolution",
                description=(
                    "Critically evaluate a proposed solution. "
                    "Returns strengths, weaknesses, and improvement suggestions. "
                    "Use to refine solutions before finalizing."
                ),
                parameter_class=CritiqueSolutionParams,
            ),
            ToolSpec(
                name="RedTeam",
                description=(
                    "Perform adversarial red-team analysis on a solution. "
                    "Identifies potential failure modes, edge cases, and vulnerabilities. "
                    "Use for robust solutions in high-stakes scenarios."
                ),
                parameter_class=RedTeamParams,
            ),
            ToolSpec(
                name="SelectBestSolution",
                description=(
                    "Compare multiple solutions and select the best one. "
                    "Provides a ranked comparison with justification. "
                    "Use when you have multiple viable solutions to choose from."
                ),
                parameter_class=SelectBestSolutionParams,
            ),
            ToolSpec(
                name="RecordReasoning",
                description=(
                    "Record a reasoning step in the thinking trace. "
                    "Helps maintain context and enables self-reflection. "
                    "Use to document important insights or decisions."
                ),
                parameter_class=RecordReasoningParams,
            ),
        ]

    def execute(self, tool_name: str, args: BaseModel) -> str:
        """Execute a tool by name with the given arguments."""
        try:
            if tool_name == "GenerateStrategies" and isinstance(args, GenerateStrategiesParams):
                return self._generate_strategies(args)
            elif tool_name == "GenerateHypotheses" and isinstance(args, GenerateHypothesesParams):
                return self._generate_hypotheses(args)
            elif tool_name == "CritiqueSolution" and isinstance(args, CritiqueSolutionParams):
                return self._critique_solution(args)
            elif tool_name == "RedTeam" and isinstance(args, RedTeamParams):
                return self._red_team(args)
            elif tool_name == "SelectBestSolution" and isinstance(args, SelectBestSolutionParams):
                return self._select_best_solution(args)
            elif tool_name == "RecordReasoning" and isinstance(args, RecordReasoningParams):
                return self._record_reasoning(args)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _generate_strategies(self, params: GenerateStrategiesParams) -> str:
        """Generate strategies for approaching a problem."""
        # This is a structured prompt that guides the agent's thinking
        # In a real implementation, this could call an LLM internally
        strategies_prompt = {
            "task": "generate_strategies",
            "problem": params.problem,
            "num_strategies": params.num_strategies,
            "constraints": params.constraints,
            "guidance": (
                "For each strategy, consider:\n"
                "1. Core approach or methodology\n"
                "2. Key assumptions being made\n"
                "3. Expected strengths and potential weaknesses\n"
                "4. When this strategy would be most effective"
            ),
            "output_format": {
                "strategies": [
                    {
                        "id": "strategy_N",
                        "name": "Brief descriptive name",
                        "approach": "Detailed description of the approach",
                        "assumptions": ["List of key assumptions"],
                        "best_when": "Conditions where this strategy excels",
                    }
                ]
            },
        }

        # Record this step
        self._strategies.append({
            "problem": params.problem,
            "constraints": params.constraints,
            "num_requested": params.num_strategies,
        })

        return json.dumps(
            {
                "instruction": "Generate strategies following this structure",
                "prompt": strategies_prompt,
                "note": (
                    "Please generate the strategies based on your knowledge and reasoning. "
                    "Format your response as a JSON object with a 'strategies' array."
                ),
            },
            indent=2,
        )

    def _generate_hypotheses(self, params: GenerateHypothesesParams) -> str:
        """Generate hypotheses for a given strategy."""
        hypotheses_prompt = {
            "task": "generate_hypotheses",
            "strategy": params.strategy,
            "context": params.context,
            "guidance": (
                "For each hypothesis, ensure it is:\n"
                "1. Specific and testable\n"
                "2. Directly related to the strategy\n"
                "3. Actionable (can be validated through analysis or implementation)\n"
                "4. Falsifiable (can be proven wrong)"
            ),
            "output_format": {
                "hypotheses": [
                    {
                        "id": "hypothesis_N",
                        "statement": "Clear hypothesis statement",
                        "rationale": "Why this hypothesis might be true",
                        "test_method": "How to validate this hypothesis",
                        "success_criteria": "What would confirm the hypothesis",
                    }
                ]
            },
        }

        self._hypotheses.append({
            "strategy": params.strategy,
            "context": params.context,
        })

        return json.dumps(
            {
                "instruction": "Generate testable hypotheses following this structure",
                "prompt": hypotheses_prompt,
            },
            indent=2,
        )

    def _critique_solution(self, params: CritiqueSolutionParams) -> str:
        """Critique a proposed solution."""
        default_criteria = [
            "correctness",
            "completeness",
            "efficiency",
            "maintainability",
            "edge_case_handling",
        ]
        criteria = params.criteria or default_criteria

        critique_prompt = {
            "task": "critique_solution",
            "solution": params.solution,
            "original_problem": params.original_problem,
            "criteria": criteria,
            "guidance": (
                "Provide a balanced critique that includes:\n"
                "1. Specific strengths (with evidence)\n"
                "2. Specific weaknesses (with evidence)\n"
                "3. Concrete suggestions for improvement\n"
                "4. Overall assessment (APPROVE, NEEDS_REVISION, REJECT)"
            ),
            "output_format": {
                "strengths": ["List of specific strengths"],
                "weaknesses": ["List of specific weaknesses"],
                "suggestions": ["List of improvement suggestions"],
                "verdict": "APPROVE | NEEDS_REVISION | REJECT",
                "confidence": "HIGH | MEDIUM | LOW",
                "summary": "One paragraph summary of the critique",
            },
        }

        self._critiques.append({
            "solution_preview": params.solution[:200] + "..." if len(params.solution) > 200 else params.solution,
            "criteria": criteria,
        })

        return json.dumps(
            {
                "instruction": "Critique the solution following this structure",
                "prompt": critique_prompt,
            },
            indent=2,
        )

    def _red_team(self, params: RedTeamParams) -> str:
        """Perform red-team analysis on a solution."""
        default_attack_vectors = [
            "edge_cases",
            "invalid_inputs",
            "resource_exhaustion",
            "race_conditions",
            "security_vulnerabilities",
            "scalability_limits",
        ]
        attack_vectors = params.attack_vectors or default_attack_vectors

        red_team_prompt = {
            "task": "red_team_analysis",
            "solution": params.solution,
            "attack_vectors": attack_vectors,
            "guidance": (
                "Think like an adversary trying to break this solution:\n"
                "1. What inputs could cause failure?\n"
                "2. What assumptions could be violated?\n"
                "3. What environmental conditions could cause issues?\n"
                "4. What are the failure modes and their severity?"
            ),
            "output_format": {
                "vulnerabilities": [
                    {
                        "category": "Attack vector category",
                        "description": "Description of the vulnerability",
                        "severity": "CRITICAL | HIGH | MEDIUM | LOW",
                        "exploit_scenario": "How this could be exploited",
                        "mitigation": "Suggested fix or mitigation",
                    }
                ],
                "overall_robustness": "ROBUST | MODERATE | FRAGILE",
                "recommendations": ["Priority-ordered list of improvements"],
            },
        }

        return json.dumps(
            {
                "instruction": "Perform adversarial red-team analysis",
                "prompt": red_team_prompt,
            },
            indent=2,
        )

    def _select_best_solution(self, params: SelectBestSolutionParams) -> str:
        """Compare solutions and select the best one."""
        default_criteria = [
            "correctness",
            "simplicity",
            "efficiency",
            "robustness",
            "maintainability",
        ]
        criteria = params.criteria or default_criteria

        selection_prompt = {
            "task": "select_best_solution",
            "solutions": [
                {"id": f"solution_{i}", "content": sol}
                for i, sol in enumerate(params.solutions, 1)
            ],
            "problem": params.problem,
            "criteria": criteria,
            "guidance": (
                "Compare solutions objectively:\n"
                "1. Score each solution on each criterion (1-10)\n"
                "2. Identify the unique strengths of each solution\n"
                "3. Consider trade-offs between criteria\n"
                "4. Provide a clear recommendation with justification"
            ),
            "output_format": {
                "comparison_matrix": {
                    "solution_id": {"criterion": "score (1-10)"}
                },
                "rankings": [
                    {
                        "rank": 1,
                        "solution_id": "solution_N",
                        "total_score": "sum of scores",
                        "key_strength": "Main advantage",
                    }
                ],
                "recommendation": {
                    "selected": "solution_N",
                    "justification": "Why this solution is best",
                    "caveats": "Any important trade-offs or considerations",
                },
            },
        }

        return json.dumps(
            {
                "instruction": "Compare and select the best solution",
                "prompt": selection_prompt,
                "num_solutions": len(params.solutions),
            },
            indent=2,
        )

    def _record_reasoning(self, params: RecordReasoningParams) -> str:
        """Record a reasoning step for context tracking."""
        entry = {
            "stage": params.stage,
            "content": params.content,
            "metadata": params.metadata or {},
        }

        self._reasoning_history.append(entry)

        return json.dumps(
            {
                "recorded": True,
                "stage": params.stage,
                "history_length": len(self._reasoning_history),
                "recent_stages": [e["stage"] for e in self._reasoning_history[-5:]],
            },
            indent=2,
        )
