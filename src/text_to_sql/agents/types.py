"""
Shared types and data models for the agentic system.
"""

from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from pydantic import (
    BaseModel,
    Field,
)


class AgenticResponse(BaseModel):
    """
    Complete response from the agentic system.
    """

    success: bool = Field(
        ...,
        description=(
            "Whether the query was successfully "
            "processed"
        ),
    )
    formatted_answer: str = Field(
        ...,
        description="The final answer/result to the user",
    )
    natural_language_summary: Optional[str] = Field(
        default=None,
        description="Plain English summary of results",
    )
    execution_chain: List["ExecutionChainStep"] = Field(
        default_factory=list,
        description=(
            "Full provenance: what each agent did"
        ),
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence in the answer (0.0 to 1.0)"
        ),
    )
    suggested_followups: List[str] = Field(
        default_factory=list,
        description=(
            "Suggested follow-up questions for the user"
        ),
    )
    error_message: Optional[str] = Field(
        default=None,
        description=(
            "Error message if processing failed"
        ),
    )
    generated_sql: Optional[str] = Field(
        default=None,
        description="Generated SQL query",
    )


class EntityExtraction(BaseModel):
    """
    LLM-extracted entities from a NL query.
    """

    tables: List[str] = Field(
        default_factory=list,
        description=(
            "Database table names referenced or "
            "implied by the query"
        ),
    )
    columns: List[str] = Field(
        default_factory=list,
        description=(
            "Column names referenced in the query"
        ),
    )
    business_entities: List[str] = Field(
        default_factory=list,
        description=(
            "Business entities mentioned "
            "(e.g., 'revenue', 'shipments')"
        ),
    )


class ExecutionChainStep(BaseModel):
    """
    A single step in the agent execution chain.
    """

    agent_name: str = Field(
        ...,
        description=(
            "Name of the agent that executed "
            "this step"
        ),
    )
    action: str = Field(
        ...,
        description=(
            "What the agent did "
            "(e.g., 'validated_permissions', "
            "'refined_query')"
        ),
    )
    input_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input to this step",
    )
    output_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Output from this step",
    )
    duration_ms: float = Field(
        default=0.0,
        description="Execution time in milliseconds",
    )
    veto_reason: Optional[str] = Field(
        default=None,
        description="If agent vetoed, reason why",
    )
    provider_ids: List[str] = Field(
        default_factory=list,
        description=(
            "OpenRouter generation_ids from LLM "
            "calls made during this step"
        ),
    )


class GeneratedSQL(BaseModel):
    """
    Structured output from SQL generation LLM.
    """

    sql: str = Field(
        ...,
        description="The generated SQL query",
    )
    explanation: str = Field(
        default="",
        description=(
            "Brief explanation of the SQL logic"
        ),
    )
    tables_used: List[str] = Field(
        default_factory=list,
        description="Tables referenced in the SQL",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Model confidence in correctness "
            "(0.0 to 1.0)"
        ),
    )


class QueryRequest(BaseModel):
    """
    User query request with context.
    """

    natural_language: str = Field(
        ...,
        description=(
            "The user's natural language query"
        ),
    )
    user_context: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "User context: role, permissions, "
            "preferences, etc."
        ),
    )
    conversation_history: List[Dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Prior conversation turns for context "
            "awareness"
        ),
    )


class SQLCritique(BaseModel):
    """
    Structured output from SQL self-critique LLM.
    """

    is_valid: bool = Field(
        ...,
        description=(
            "Whether the SQL is correct"
        ),
    )
    issues: List[str] = Field(
        default_factory=list,
        description=(
            "List of issues found in the SQL"
        ),
    )
    corrected_sql: Optional[str] = Field(
        default=None,
        description=(
            "Corrected SQL if issues were found"
        ),
    )
