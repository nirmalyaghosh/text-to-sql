"""
Security & Governance Agent: High-agency security agent with veto power.

Responsibilities:
- Real-time permission validation
- PII/data masking requirements
- Query safety analysis (read-only enforcement)
- Compliance logging
- Risk assessment scoring
"""

import json
import os
import re
import time

from typing import (
    Any,
    Dict,
    Optional,
)

from text_to_sql.agents.base import BaseAgent
from text_to_sql.agents.types import QueryRequest
from text_to_sql.app_logger import get_logger
from text_to_sql.llm_config import (
    get_client,
    get_model_name,
    load_config,
)
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.usage_tracker import log_llm_response


logger = get_logger(__name__)


class SecurityGovernanceAgent(BaseAgent):
    """
    High-agency security agent with veto power.

    Enforces role-based access control, prevents unsafe operations,
    and applies data masking rules.
    """

    def __init__(self, extended_pii: bool = False):
        """
        Initialize the Security & Governance Agent.
        """
        system_prompt = get_prompt("security_governance")
        super().__init__(
            "Security & Governance", system_prompt
        )
        self.policies = self._load_security_policies()
        self.pii_patterns = self._load_pii_patterns()
        self.pii_field_patterns = self._load_pii_field_patterns(extended_pii)

    async def _assess_risk(self, query: str) -> float:
        """
        Helper function used to calculate a risk score
        for the query (0.0 to 1.0).

        Args:
            query: The query being assessed

        Returns:
            Risk score (0.0 = safe, 1.0 = dangerous)
        """
        risk_score = 0.0

        # Heuristics for risk scoring
        query_lower = query.lower()

        # SQL JOINs increase risk (data exposure).
        # Pattern matches JOIN <table> ON to avoid
        # NL false positives like "join date".
        join_count = len(re.findall(
            r'\bjoin\s+\w+\s+on\b', query_lower
        ))
        risk_score += join_count * 0.05

        # Aggregates are generally safe
        if any(
            agg in query_lower
            for agg in ["count", "sum", "avg", "max", "min"]
        ):
            risk_score -= 0.1

        # Subqueries increase complexity
        if "(" in query and "SELECT" in query.upper():
            risk_score += 0.1

        return max(0.0, min(1.0, risk_score))

    async def audit_semantic_intent(
        self,
        nl_query: str,
        generated_sql: str,
    ) -> Dict[str, Any]:
        """
        Semantic output audit: compare generated SQL
        columns against the user's original request
        using a small LLM. Flags unrequested columns,
        especially PII.

        Args:
            nl_query: The user's natural language query
            generated_sql: The SQL that was produced

        Returns:
            {'safe': bool, 'reason': str}
        """
        try:
            config = load_config()
            eps = config.get_role_endpoints(
                project="default",
                role="semantic_audit",
            )
            if not eps:
                logger.warning("No semantic_audit endpoint configured, skipping")
                return {"safe": True}
            ep = eps[0]
            logger.info("Semantic audit: %s via %s", ep.model, ep.provider)

            client = get_client(endpoint_name=ep.name, config=config)
            model = get_model_name(endpoint_name=ep.name, config=config)
            create_kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": get_prompt("semantic_audit")},
                    {"role": "user", "content": (
                        f"/no_think\nUSER_QUERY: {nl_query}\n\n"
                        f"GENERATED_SQL: {generated_sql}"
                    )},
                ],
                "temperature": 0.0,
                "max_tokens": 200,
            }
            run_tag = os.environ.get("OPENROUTER_RUN_TAG", "")
            if run_tag:
                create_kwargs["user"] = run_tag
            provider = os.environ.get("OPENROUTER_PROVIDER", "")
            if provider:
                create_kwargs["extra_body"] = {
                    "provider": json.loads(provider),
                }
            response = client.chat.completions.create(**create_kwargs)

            u = response.usage
            if u:
                log_llm_response(
                    request_id="semantic_audit",
                    model=model,
                    question=nl_query[:200],
                    usage={
                        "prompt_tokens": u.prompt_tokens,
                        "completion_tokens": u.completion_tokens,
                        "total_tokens": u.total_tokens,
                    },
                    generated_sql=generated_sql[:200],
                    purpose="semantic_audit",
                )

            result = self._parse_audit_response(
                response.choices[0].message.content.strip()
            )
            if hasattr(response, "id") and response.id:
                result["provider_id"] = response.id
            return result

        except json.JSONDecodeError as e:
            logger.warning("Semantic audit: invalid JSON: %s", e)
            return {"safe": True}
        except Exception as e:
            logger.warning("Semantic audit unavailable: %s", e)
            return {"safe": True}

    def _parse_audit_response(
        self,
        content: str,
    ) -> Dict[str, Any]:
        """
        Helper function used to parse the JSON
        response from the semantic audit LLM.
        """
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0].strip()

        result = json.loads(content)
        if result.get("safe", True):
            return {"safe": True}

        reason = result.get("reason", "Unrequested columns in SQL")
        extra = result.get("extra_columns", [])
        if extra:
            reason = f"{reason} (columns: {', '.join(extra)})"
        logger.warning("Semantic audit flagged: %s", reason)
        return {"safe": False, "reason": reason}

    async def audit_generated_sql(
        self,
        sql: str,
        user_role: str = "analyst",
    ) -> Dict[str, Any]:
        """
        Post-generation audit: verify generated SQL
        is read-only and does not expose unauthorized
        PII.

        Args:
            sql: The generated SQL string
            user_role: Role of the requesting user

        Returns:
            {'safe': bool, 'reason': str}
        """
        safety = await self._check_query_safety(sql)
        if not safety.get("safe"):
            return safety

        if self._can_access_pii(user_role):
            return {"safe": True}

        pii = await self._detect_pii_access(sql)
        if pii.get("found_pii"):
            pii_str = ", ".join(pii["pii_tables"])
            return {
                "safe": False,
                "reason": (
                    "Generated SQL accesses PII"
                    f" ({pii_str}). Role "
                    f"'{user_role}' not authorized."
                ),
            }

        return {"safe": True}

    def _build_allowed_result(
        self,
        query: str,
        step_start: float,
    ) -> Dict[str, Any]:
        """
        Helper function used to build the success
        result after all security checks pass.
        """
        duration_ms = (
            (time.time() - step_start) * 1000
        )
        logger.info("Security checks passed")
        return {
            "allowed": True,
            "refined_query": query,
            "execution_step": self.create_execution_step(
                action="security_validation_passed",
                input_data={"query": query},
                output_data={},
                duration_ms=duration_ms,
            ),
        }

    def _build_security_error(
        self,
        previous_results: Dict[str, Any],
        error: str,
        step_start: float,
    ) -> Dict[str, Any]:
        """
        Helper function used to build the result
        for unexpected errors during security checks.
        """
        duration_ms = (
            (time.time() - step_start) * 1000
        )
        query = (
            previous_results
            .get("refinement", {})
            .get("refined_query", "")
        )
        return {
            "allowed": False,
            "veto_reason": f"Security check failed: {error}",
            "execution_step": self.create_execution_step(
                action="security_check_error",
                input_data={"query": query},
                output_data={"error": error},
                veto_reason=(
                    "Internal security check error"
                ),
                duration_ms=duration_ms,
            ),
        }

    def _can_access_pii(self, role: str) -> bool:
        """
        Helper function used to check if a user role
        can access PII.
        """
        return role == "admin"

    async def _check_access_control(
        self, user_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Helper function used to verify user has
        permission to execute the query.

        Args:
            user_context: User role, permissions, etc.

        Returns:
            {'allowed': bool, 'reason': str}
        """
        user_role = user_context.get("role", "user")

        # Phase 1: Simple RBAC
        # Only 'analyst' and 'admin' roles allowed in Phase 1
        allowed_roles = ["analyst", "admin"]
        if user_role not in allowed_roles:
            return {
                "allowed": False,
                "reason": (
                    f"Role '{user_role}' not authorized. "
                    f"Allowed roles: {allowed_roles}"
                ),
            }

        return {"allowed": True}

    async def _check_pii_gate(
        self,
        query: str,
        user_role: str,
        step_start: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Helper function used to check PII access and
        return a veto if the user role is not
        authorized. Returns None if passed.
        """
        pii_check = await self._detect_pii_access(query)
        if not pii_check.get("found_pii"):
            return None
        if self._can_access_pii(user_role):
            return None

        pii_str = ", ".join(pii_check["pii_tables"])
        reason = (
            f"Query attempts to access PII "
            f"({pii_str}). Role '{user_role}' "
            f"not authorized."
        )
        return self._veto(
            action="pii_access_blocked",
            query=query,
            reason=reason,
            output_data={
                "pii_tables": pii_check.get("pii_tables", [])
            },
            veto_reason="Unauthorized PII access",
            step_start=step_start,
        )

    async def _check_query_safety(self, query: str) -> Dict[str, Any]:
        """
        Helper function used to ensure the query is
        read-only. Uses SQL-contextual patterns
        (e.g. DELETE FROM, DROP TABLE) instead of
        bare keywords to avoid false positives on
        natural language input.

        Args:
            query: The query being checked

        Returns:
            {'safe': bool, 'reason': str}
        """
        dangerous_patterns = [
            (r"\bALTER\s+TABLE\b", "ALTER TABLE"),
            (
                r"\bCREATE\s+(OR\s+REPLACE\s+)?"
                r"(TABLE|INDEX|VIEW|DATABASE"
                r"|SCHEMA|PROCEDURE|FUNCTION"
                r"|TRIGGER)\b",
                "CREATE",
            ),
            (r"\bDELETE\s+FROM\b", "DELETE FROM"),
            (
                r"\bDROP\s+(TABLE|INDEX|VIEW"
                r"|DATABASE|SCHEMA|PROCEDURE"
                r"|FUNCTION|TRIGGER)\b",
                "DROP",
            ),
            (r"\bINSERT\s+INTO\b", "INSERT INTO"),
            (r"\bTRUNCATE\b", "TRUNCATE"),
            (r"\bUPDATE\s+\w+\s+SET\b", "UPDATE...SET"),
        ]
        query_upper = query.upper()

        for pattern, label in dangerous_patterns:
            if re.search(pattern, query_upper):
                return {
                    "safe": False,
                    "reason": (
                        "Query contains destructive "
                        f"pattern: {label}. Only "
                        "SELECT queries allowed."
                    ),
                }

        return {"safe": True}

    async def _check_risk_gate(
        self,
        query: str,
        step_start: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Helper function used to check risk score and
        return a veto if it exceeds the threshold.
        Returns None if passed.
        """
        risk_score = await self._assess_risk(query)
        threshold = self.policies.get("risk_threshold", 0.7)
        if risk_score <= threshold:
            return None

        reason = (
            f"Risk score {risk_score:.2f} exceeds "
            f"threshold {threshold}"
        )
        result = self._veto(
            action="risk_assessment_blocked",
            query=query,
            reason=reason,
            output_data={"risk_score": risk_score},
            veto_reason=f"High risk: {risk_score:.2f}",
            step_start=step_start,
        )
        result["requires_approval"] = True
        return result

    async def _detect_pii_access(self, query: str) -> Dict[str, Any]:
        """
        Helper function used to detect if the query
        attempts to access PII tables or columns.

        Args:
            query: The query being checked

        Returns:
            {'found_pii': bool, 'pii_tables': [list]}
        """
        query_lower = query.lower()
        pii_tables = []
        pii_columns = []

        # Check for PII field mentions
        detected_pii = []
        for pii_type, patterns in self.pii_field_patterns.items():
            for pattern in patterns:
                if pattern in query_lower:
                    detected_pii.append(pii_type)
                    break

        # Map detected PII to tables via
        # self.pii_patterns (table -> PII types)
        if detected_pii:
            for tbl, cols in self.pii_patterns.items():
                if not any(p in cols for p in detected_pii):
                    continue
                stem = tbl[:-1] if tbl.endswith("s") else tbl
                if stem in query_lower or tbl in query_lower:
                    pii_tables.append(tbl)
                    pii_columns.extend(detected_pii)

            # If PII fields detected but table context unclear,
            # assume risky and flag it
            if detected_pii and not pii_tables:
                pii_tables.append("unknown")
                pii_columns.extend(detected_pii)

        if pii_tables:
            logger.warning(f"PII access detected in query: {pii_tables}")

        return {
            "found_pii": len(pii_tables) > 0,
            "pii_tables": pii_tables,
            "pii_columns": list(set(pii_columns)),
        }

    async def _execute_internal(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute security checks on the query.

        Runs access control, query safety, PII detection,
        and risk assessment in sequence. Any check can
        veto the query.
        """
        step_start = time.time()

        try:
            refined_query = (
                previous_results
                .get("refinement", {})
                .get(
                    "refined_query",
                    request.natural_language,
                )
            )
            user_role = request.user_context.get(
                "role", "user"
            )

            access = await self._check_access_control(
                request.user_context,
            )
            if not access.get("allowed"):
                reason = access.get("reason")
                return self._veto(
                    action="access_control_check_blocked",
                    query=refined_query,
                    reason=reason,
                    output_data={"reason": reason},
                    veto_reason=reason,
                    step_start=step_start,
                )

            safety = await self._check_query_safety(
                refined_query
            )
            if not safety.get("safe"):
                reason = safety.get("reason")
                return self._veto(
                    action="safety_check_blocked",
                    query=refined_query,
                    reason=reason,
                    output_data={"reason": reason},
                    veto_reason=reason,
                    step_start=step_start,
                )

            pii_veto = await self._check_pii_gate(
                refined_query, user_role, step_start
            )
            if pii_veto:
                return pii_veto

            risk_veto = await self._check_risk_gate(
                refined_query, step_start
            )
            if risk_veto:
                return risk_veto

            return self._build_allowed_result(
                refined_query, step_start
            )

        except Exception as e:
            logger.error(
                f"Security check error: {str(e)}"
            )
            return self._build_security_error(
                previous_results, str(e), step_start
            )

    def _load_pii_patterns(self) -> Dict[str, list]:
        """
        Helper function used to load PII patterns
        per table.
        """
        return {
            "customers": [
                "email", "phone", "address",
                "national_id", "credit_card",
            ],
            "employees": [
                "national_id", "salary",
                "dob", "address",
            ],
        }

    def _load_pii_field_patterns(
        self, extended_pii: bool = False,
    ) -> Dict[str, list]:
        """
        Helper function used to load NL synonym
        patterns for each PII type. When
        extended_pii is True, includes national ID
        patterns for multiple countries.
        """
        if extended_pii:
            national_id = [
                "nric",  # Singapore
                "shenfenzheng", "身份证号",  # China
                "aadhaar", "aadhar",  # India
                "mykad", "my kad",  # Malaysia
                "cccd",  # Vietnam
                "nik", "ktp",  # Indonesia
                "บัตรประชาชน",  # Thailand
                "ssn", "social security",  # US
            ]
        else:
            national_id = [
                "ssn", "social security",
            ]
        return {
            "email": [
                "email", "e-mail", "email address",
            ],
            "phone": [
                "phone", "phone number", "telephone",
            ],
            "address": [
                "address", "street", "city", "zip",
            ],
            "national_id": national_id,
            "salary": [
                "salary", "compensation", "wage",
            ],
            "dob": [
                "dob", "date of birth", "birth date",
            ],
            "credit_card": [
                "credit card", "card number",
                "cc number",
            ],
        }

    def _load_security_policies(self) -> Dict[str, Any]:
        """
        Helper function used to load security policies.
        """
        return {
            "risk_threshold": 0.7,
            "require_approval_above_risk": 0.7,
            "allowed_read_only": True,
            "pii_masking_enabled": True,
        }

    def _veto(
        self,
        action: str,
        query: str,
        reason: str,
        output_data: Dict[str, Any],
        veto_reason: str,
        step_start: float,
    ) -> Dict[str, Any]:
        """
        Helper function used to build a standard
        security veto response.
        """
        duration_ms = (
            (time.time() - step_start) * 1000
        )
        return {
            "allowed": False,
            "veto_reason": reason,
            "execution_step": self.create_execution_step(
                action=action,
                input_data={"query": query},
                output_data=output_data,
                veto_reason=veto_reason,
                duration_ms=duration_ms,
            ),
        }
