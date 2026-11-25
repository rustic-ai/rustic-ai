"""Synchronous Uni-DB execution and recovery. No guild authorization policy."""

from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
import json
import math
import re
import threading

from jsonschema import Draft202012Validator
import uni_db

from . import models as m
from .serialization import bounded, canonical, encode

RECEIPT_LABEL = "RusticUniDBOperation"
RECEIPT_PREFIX = "__rustic_unidb:"
STAT_FIELDS = (
    "nodes_created",
    "nodes_deleted",
    "relationships_created",
    "relationships_deleted",
    "properties_set",
    "properties_removed",
    "labels_added",
    "labels_removed",
)


class RuntimeFailure(Exception):
    def __init__(self, code: str, stage: str, message: str, effect: str = "not_started", details=None):
        super().__init__(message)
        self.code, self.stage, self.effect = code, stage, effect
        self.details = details or {}


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value):
        raise RuntimeFailure("invalid_parameters", "validate", "Invalid database identifier")
    return value


class UniDBRuntime:
    def __init__(self, db, binding_id: str, bootstrap: dict, receipts: dict):
        self.db, self.binding_id = db, binding_id
        self.bootstrap, self.receipts = bootstrap, receipts
        self.native_version = version("uni-db")
        self.state = "initializing"
        self.lock = threading.RLock()
        self.config = m.UniDBAgentConfig(binding_id=binding_id)
        self.operations: dict[str, m.Operation] = {}
        self.rule_program_ids = [p["id"] for p in bootstrap.get("rule_programs", [])]
        self.rule_digest = sha256(canonical(bootstrap.get("rule_programs", [])).encode()).hexdigest()
        try:
            self._bootstrap()
            self.state = "ready"
        except Exception:
            self.state = "failed"
            self.db.shutdown()
            raise

    def configure(self, config: m.UniDBAgentConfig):
        if config.binding_id != self.binding_id:
            raise ValueError("Agent and resolver binding_id differ")
        self.config = config
        self.operations = {op.name: op for op in config.operation_catalog.operations}

    def _bootstrap(self):
        policy = self.bootstrap.get("policy", "verify_existing")
        definitions = self.bootstrap.get("schema", {})
        if policy not in ("apply_to_new", "verify_existing"):
            raise ValueError("Unsupported bootstrap policy")
        for label in definitions.get("labels", []):
            identifier(label["name"])
            if policy == "apply_to_new":
                builder = self.db.schema().label(label["name"])
                for prop in label.get("properties", []):
                    method = builder.property_nullable if prop.get("nullable", False) else builder.property
                    method(identifier(prop["name"]), prop["type"])
                builder.apply()
            self._verify_definition(label, self.db.get_label_info(label["name"]))
        for edge in definitions.get("edge_types", []):
            identifier(edge["name"])
            if policy == "apply_to_new":
                builder = self.db.schema().edge_type(edge["name"], edge["source_labels"], edge["target_labels"])
                for prop in edge.get("properties", []):
                    method = builder.property_nullable if prop.get("nullable", False) else builder.property
                    method(identifier(prop["name"]), prop["type"])
                builder.apply()
            info = self.db.get_edge_type_info(edge["name"])
            self._verify_definition(edge, info)
            if set(info.source_labels) != set(edge["source_labels"]) or set(info.target_labels) != set(
                edge["target_labels"]
            ):
                raise ValueError("Existing edge endpoints differ from bootstrap")
        if self.receipts.get("mode", "same_transaction") != "same_transaction":
            raise ValueError("Only same_transaction ordinary receipts are supported")
        if self.receipts.get("namespace", "__rustic_unidb") != "__rustic_unidb":
            raise ValueError("Receipt namespace must be __rustic_unidb")
        if policy == "apply_to_new":
            self.db.schema().label(RECEIPT_LABEL).property("fingerprint", "string").property("record", "string").apply()
        elif not self.db.label_exists(RECEIPT_LABEL):
            raise ValueError("Existing store lacks connector receipt schema")
        programs = self.bootstrap.get("rule_programs", [])
        if policy == "apply_to_new":
            for program in programs:
                self.db.rules().register(program["text"])
            self._put_record(
                self.db.session(),
                RECEIPT_PREFIX + "bootstrap",
                self.rule_digest,
                {"revision": self.bootstrap.get("revision"), "rule_digest": self.rule_digest},
            )
        else:
            record = self._record(self.db.session(), RECEIPT_PREFIX + "bootstrap")
            if programs and (not record or record["fingerprint"] != self.rule_digest):
                raise ValueError("Existing rule program digest differs from bootstrap")
            for program in programs:
                # Compile supplied text without replacing the persisted registry.
                self.db.session().compile_locy(program["text"])
        self.db.flush()

    @staticmethod
    def _verify_definition(definition, info):
        if info is None:
            raise ValueError("Expected schema definition is absent")
        actual = {p.name: p for p in info.properties}
        for prop in definition.get("properties", []):
            observed = actual.get(prop["name"])
            if not observed or observed.data_type != prop["type"] or observed.nullable != prop.get("nullable", False):
                raise ValueError("Existing property definition differs from bootstrap")

    @staticmethod
    def _record(session, key):
        rows = session.query(
            f"MATCH (r:{RECEIPT_LABEL} {{ext_id: $key}}) RETURN r.fingerprint AS fingerprint, r.record AS record",
            {"key": key},
        )
        return rows[0].to_dict() if rows else None

    @staticmethod
    def _put_record(session, key, fingerprint, record):
        with session.tx() as tx:
            tx.execute(
                f"CREATE (:{RECEIPT_LABEL} {{ext_id: $key, fingerprint: $fingerprint, record: $record}})",
                {"key": key, "fingerprint": fingerprint, "record": canonical(record)},
            )
            tx.commit()

    @staticmethod
    def _update_record(session, key, record):
        with session.tx() as tx:
            tx.execute(
                f"MATCH (r:{RECEIPT_LABEL} {{ext_id: $key}}) SET r.record = $record",
                {"key": key, "record": canonical(record)},
            )
            tx.commit()

    def _identity(self, request, caller, definition):
        key = RECEIPT_PREFIX + sha256(canonical([self.binding_id, caller, request.operation_id]).encode()).hexdigest()
        content = request.model_dump(exclude={"request_id", "correlation_id", "operation_id", "limits"})
        fingerprint = sha256(
            canonical({"request": content, "definition": definition, "rules": self.rule_digest}).encode()
        ).hexdigest()
        return key, fingerprint

    def _replay(self, session, key, fingerprint):
        prior = self._record(session, key)
        if not prior:
            return None
        if prior["fingerprint"] != fingerprint:
            raise RuntimeFailure("operation_id_conflict", "receipt", "Operation ID identifies different content")
        record = json.loads(prior["record"])
        if record["state"] == "rolled_back":
            return None
        if record["state"] != "completed":
            load_id = record.get("load_id")
            applied = self.db.bulk_load_applied(load_id) if load_id else None
            raise RuntimeFailure(
                "operation_outcome_unknown",
                "receipt",
                "Inspect operation status; do not redispatch",
                "committed" if applied else "unknown",
                {"load_id": load_id, "applied": applied},
            )
        result = record["result"]
        result["replayed"] = True
        result["commit"] = {"metadata_available": False}
        return result

    def limits(self, request):
        effective = self.config.limits.model_dump()
        for name, value in (request.limits or {}).items():
            if name not in effective or type(value) is not int or value <= 0 or value > effective[name]:
                raise RuntimeFailure("invalid_parameters", "validate", "Limits may only reduce configured bounds")
            effective[name] = value
        if len(canonical(request.model_dump()).encode()) > effective["max_input_bytes"]:
            raise RuntimeFailure("input_limit", "validate", "Request exceeds max_input_bytes")
        return effective

    def metadata(self):
        return {
            "native_version": self.native_version,
            "catalog_revision": self.config.operation_catalog.revision,
            "catalog_digest": sha256(canonical(self.config.operation_catalog.model_dump()).encode()).hexdigest(),
            "rule_program_ids": self.rule_program_ids,
            "rule_digest": self.rule_digest,
            "view": {"kind": "live", "snapshot_id": None},
        }

    def execute(self, request: m.Request, caller: str):
        with self.lock:
            if self.state != "ready":
                raise RuntimeFailure("binding_unavailable", "admit", "Database is not ready")
            limits = self.limits(request)
            session = self.db.session()
            if isinstance(request, m.NamedRequest):
                if request.view not in (None, {"kind": "live"}):
                    raise RuntimeFailure(
                        "unsupported_view", "validate", "V1 supports live primary and scratch scenarios"
                    )
                op = self.operations.get(request.operation)
                if not op:
                    raise RuntimeFailure("unknown_operation", "validate", "Operation is not configured")
                expected = {
                    m.DBQueryRequest: "query",
                    m.DBQueryPlanRequest: "query",
                    m.DBQueryProfileRequest: "query",
                    m.DBEvaluateRequest: "evaluate",
                    m.DBExplainRequest: "explain",
                    m.DBMutateRequest: "mutation",
                    m.DBScenarioRequest: "scenario",
                }[type(request)]
                if op.kind != expected:
                    raise RuntimeFailure("invalid_request", "validate", "Operation kind differs from message family")
                errors = list(Draft202012Validator(op.parameters_schema).iter_errors(request.params))
                if errors:
                    raise RuntimeFailure("invalid_parameters", "validate", errors[0].message)
                if isinstance(request, (m.DBQueryPlanRequest, m.DBQueryProfileRequest)):
                    result = self._diagnostic(session, request, op, limits)
                elif op.kind == "mutation":
                    result = self._mutate(session, request, caller, op, limits)
                elif op.kind == "scenario":
                    result = self._scenario(session, request, op, limits)
                elif op.kind == "query":
                    result = self._query(session, op.query, request.params, limits, op.columns)
                else:
                    result = self._logic(session, op.program, request.params, limits, op.kind == "explain", op.columns)
            else:
                result = self._primitive(session, request, caller, limits)
            try:
                return bounded(result, limits["max_output_bytes"])
            except (ValueError, TypeError) as exc:
                effect = result.get("effect", "not_started")
                raise RuntimeFailure("serialization_failure", "serialize", str(exc), effect) from exc

    def _query(self, scope, query, params, limits, expected=None):
        builder = (
            scope.query_with(query).timeout(limits["timeout_ms"] / 1000).max_memory(limits["max_query_memory_bytes"])
        )
        for key, value in params.items():
            builder.param(key, value)
        native = builder.fetch_all()
        return self._query_result(native, limits, expected)

    def _query_result(self, native, limits, expected=None, profile=False):
        columns = native.columns
        source = "native"
        if profile and not native and not columns and expected:
            columns, source = expected, "catalog"
        if expected and columns != expected:
            raise RuntimeFailure("result_contract", "profile" if profile else "query", "Unexpected result columns")
        rows = [encode(row) for row in native[: limits["max_rows"]]]
        truncated = len(native) > limits["max_rows"]
        return {
            "columns": columns,
            **({"columns_source": source} if profile else {}),
            "rows": rows,
            "returned_count": len(rows),
            "truncated": truncated,
            "complete": not truncated,
            "warnings": [{"source": "native", "code": w.code, "message": w.message} for w in native.warnings],
        }

    def _diagnostic(self, session, request, op, limits):
        planning = isinstance(request, m.DBQueryPlanRequest)
        stage = "plan" if planning else "profile"
        if planning and set(request.limits or {}) - {"max_input_bytes", "max_output_bytes"}:
            raise RuntimeFailure("unsupported_limit", "validate", "Planning supports only input/output byte limits")
        builder = session.query_with(op.query).params(request.params)
        try:
            if planning:
                native = builder.explain()
            else:
                rows, native = (
                    builder.timeout(limits["timeout_ms"] / 1000).max_memory(limits["max_query_memory_bytes"]).profile()
                )
        except Exception as exc:
            raise RuntimeFailure("native_error", stage, str(exc)) from exc
        try:
            if planning:
                return {
                    "executed": False,
                    "plan": encode(native),
                    "parameter_values_applied": False,
                    "planning_timeout_enforced": False,
                    "planning_memory_enforced": False,
                    "enforced_limits": {key: limits[key] for key in ("max_input_bytes", "max_output_bytes")},
                }
            return {
                "executed": True,
                "query": self._query_result(rows, limits, op.columns, profile=True),
                "profile": dict(encode(native), query_metrics=encode(rows.metrics)),
            }
        except (ValueError, TypeError) as exc:
            raise RuntimeFailure("serialization_failure", "serialize", str(exc)) from exc

    def _logic(self, scope, program, params, limits, explain=False, expected=None):
        if explain:
            # The Locy EXPLAIN command path does not propagate builder parameters into its filters.
            # Bind scalar VALUES only; quoted strings/comments are never rewritten.
            token = re.compile(
                r"('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`[^`]*`|//[^\n]*|/\*.*?\*/)|\$([A-Za-z_][A-Za-z0-9_]*)", re.S
            )

            def replace(match):
                if match.group(1):
                    return match.group(1)
                value = params[match.group(2)]
                if value is not None and type(value) not in (str, int, float, bool):
                    raise RuntimeFailure("invalid_parameters", "explain", "EXPLAIN keys require scalar values")
                return canonical(value)

            program = token.sub(replace, program)
        builder = (
            scope.locy_with(program).timeout(limits["timeout_ms"] / 1000).max_memory(limits["max_query_memory_bytes"])
        )
        for key, value in params.items():
            builder.param(key, value)
        native = builder.run()
        if native.incomplete or native.timed_out:
            raise RuntimeFailure(
                "incomplete_evaluation",
                "evaluate",
                "Native evaluation is incomplete",
                details={"warnings": encode(native.warnings), "compile_warnings": encode(native.compile_warnings)},
            )
        commands = encode(native.command_results)
        if explain:
            proofs = [c for c in commands if c.get("type") == "explain"]
            tree = proofs[0].get("tree", {}) if proofs else {}
            if not tree or not (tree.get("bindings") or tree.get("children") or tree.get("graph_fact")):
                raise RuntimeFailure("no_derivation", "explain", "No derivation exists for this key")
            return {
                "derivation_found": True,
                "proof": {"media_type": "application/json", "value": proofs[0]},
                "truncated": False,
                "warnings": encode(native.warnings),
                "compile_warnings": encode(native.compile_warnings),
            }
        normalized = []
        for command in commands:
            if command.get("type") == "query":
                rows = command.get("rows", [])
                columns = command.get("columns") or (list(rows[0]) if rows else expected or [])
                if expected and set(columns) != set(expected):
                    raise RuntimeFailure("result_contract", "evaluate", "Unexpected result columns")
                if expected:
                    columns = expected
                normalized.append(
                    {
                        "kind": "query",
                        "columns": columns,
                        "rows": rows[: limits["max_rows"]],
                        "returned_count": min(len(rows), limits["max_rows"]),
                        "truncated": len(rows) > limits["max_rows"],
                        "complete": len(rows) <= limits["max_rows"],
                    }
                )
            else:
                normalized.append({"kind": command.get("type", "unknown"), "native": command})
        return {
            "commands": normalized,
            "materialized": False,
            "rule_program_ids": self.rule_program_ids,
            "warnings": encode(native.warnings),
            "compile_warnings": encode(native.compile_warnings),
        }

    def _statement(self, scope, statement, params, limits):
        if statement.kind == "locy":
            return self._logic(scope, statement.text, params, limits)
        return self._query(scope, statement.text, params, limits)

    def _checks(self, tx, checks, params, limits, phase):
        for check in checks:
            if check.phase != phase:
                continue
            result = self._statement(tx, check.statement, params, limits)
            if "commands" in result:
                result = result["commands"][0]
            rows = result["rows"]
            expected = check.expect
            valid = result["complete"] and len(rows) == expected.row_count
            if valid and expected.operator:
                for row in rows:
                    actual = row.get(expected.column)
                    if expected.operator == "eq":
                        valid &= actual == expected.value
                    else:
                        valid &= isinstance(actual, (int, float)) and math.isclose(
                            actual, expected.value, rel_tol=0, abs_tol=expected.abs_tolerance
                        )
            if not valid:
                raise RuntimeFailure("check_failed", "check", "Configured transaction assertion failed", "rolled_back")

    def _mutate(self, session, request, caller, op, limits):
        if len(op.statements) > limits["max_statements"]:
            raise RuntimeFailure("statement_limit", "validate", "Too many statements")
        key, fingerprint = self._identity(request, caller, op.model_dump())
        replay = self._replay(session, key, fingerprint)
        if replay:
            return replay
        pending = {"state": "in_progress", "operation_id": request.operation_id}
        if self._record(session, key):
            self._update_record(session, key, pending)
        else:
            self._put_record(session, key, fingerprint, pending)
        commit_attempted = False
        result = None
        try:
            with session.tx_with().timeout(limits["timeout_ms"] / 1000).start() as tx:
                self._checks(tx, op.checks, request.params, limits, "pre")
                stats = {field: 0 for field in STAT_FIELDS}
                for index, statement in enumerate(op.statements):
                    if statement.kind != "cypher":
                        raise RuntimeFailure("unsupported_operation", "validate", "Ordinary mutations require Cypher")
                    native = (
                        tx.execute_with(statement.text)
                        .params(request.params)
                        .timeout(limits["timeout_ms"] / 1000)
                        .max_memory(limits["max_query_memory_bytes"])
                        .run()
                    )
                    current = {field: getattr(native, field) for field in STAT_FIELDS}
                    for expectation in op.statement_expectations:
                        if expectation["statement_index"] == index:
                            if any(
                                current[name] != value
                                for name, value in expectation.items()
                                if name != "statement_index"
                            ):
                                raise RuntimeFailure(
                                    "check_failed", "mutate", "Mutation statistics differ", "rolled_back"
                                )
                    for field in stats:
                        stats[field] += current[field]
                self._checks(tx, op.checks, request.params, limits, "post")
                result = bounded(
                    {
                        "operation_id": request.operation_id,
                        "effect": "committed",
                        "replayed": False,
                        "statistics": stats,
                    },
                    limits["max_output_bytes"],
                )
                tx.execute(
                    f"MATCH (r:{RECEIPT_LABEL} {{ext_id: $key}}) SET r.record = $record",
                    {"key": key, "record": canonical({"state": "completed", "result": result})},
                )
                commit_attempted = True
                commit = tx.commit()
            result["commit"] = {
                "version": str(commit.version),
                "rules_promoted": commit.rules_promoted,
                "rule_promotion_errors": [
                    {"rule_text": e.rule_text, "error": e.error} for e in commit.rule_promotion_errors
                ],
            }
            return result
        except RuntimeFailure:
            if not commit_attempted:
                self._update_record(session, key, {"state": "rolled_back", "operation_id": request.operation_id})
            raise
        except Exception as exc:
            # A receipt is authoritative even when commit reporting failed.
            if commit_attempted:
                replay = self._replay(session, key, fingerprint)
                if replay:
                    return replay
            known_conflict = isinstance(exc, (uni_db.UniTransactionConflictError, uni_db.UniConstraintConflictError))
            effect = "unknown" if commit_attempted and not known_conflict else "rolled_back"
            if effect == "rolled_back":
                self._update_record(session, key, {"state": "rolled_back", "operation_id": request.operation_id})
            raise RuntimeFailure(
                "operation_outcome_unknown" if effect == "unknown" else "mutation_failed",
                "commit" if commit_attempted else "mutate",
                str(exc),
                effect,
            ) from exc

    def _scenario(self, session, request, op, limits):
        if len(op.mutations) > limits["max_statements"]:
            raise RuntimeFailure("statement_limit", "validate", "Too many scenario statements")
        with session.scratch() as tx:

            def evaluation(statement):
                result = self._statement(tx, statement, request.params, limits)
                if "commands" in result and len(result["commands"]) == 1:
                    return dict(
                        result["commands"][0], warnings=result["warnings"], compile_warnings=result["compile_warnings"]
                    )
                return result

            before = [evaluation(s) for s in op.before]
            for statement in op.mutations:
                if statement.kind != "cypher":
                    raise RuntimeFailure("unsupported_operation", "scenario", "Scratch mutations require Cypher")
                tx.execute_with(statement.text).params(request.params).timeout(limits["timeout_ms"] / 1000).max_memory(
                    limits["max_query_memory_bytes"]
                ).run()
            after = [evaluation(s) for s in op.after]
            result = bounded(
                {
                    "isolation": "scratch",
                    "persisted": False,
                    "cleanup": "completed",
                    "before": before,
                    "after": after,
                    "warnings": op.warnings,
                },
                limits["max_output_bytes"],
            )
            tx.rollback()
        return result

    def _journaled(self, session, request, caller, callback):
        key, fingerprint = self._identity(request, caller, {"primitive": type(request).__name__})
        replay = self._replay(session, key, fingerprint)
        if replay:
            return replay
        record = {"state": "in_progress", "operation_id": request.operation_id}
        self._put_record(session, key, fingerprint, record)
        try:
            result = callback(record, lambda: self._update_record(self.db.session(), key, record))
            result.update(operation_id=request.operation_id, effect="committed", replayed=False)
            prepared = bounded(result, self.config.limits.max_output_bytes)
            self._update_record(session, key, {"state": "completed", "result": prepared})
            return prepared
        except Exception as exc:
            load_id = record.get("load_id")
            applied = self.db.bulk_load_applied(load_id) if load_id else None
            # Do not imply rollback for partially applied DDL or bulk outcomes.
            raise RuntimeFailure(
                "operation_outcome_unknown",
                "admin_or_bulk",
                str(exc),
                "committed" if applied else "unknown",
                {"load_id": load_id, "applied": applied},
            ) from exc

    def _primitive(self, session, request, caller, limits):
        if isinstance(request, m.DBHealthRequest):
            return {
                "state": self.state,
                "database_ready": True,
                "wal_enabled": self.db.config().get("wal_enabled"),
                "shutdown_hook_integrated": False,
            }
        if isinstance(request, m.DBCapabilitiesRequest):
            return {
                "protocol_version": 1,
                "native_version": self.native_version,
                "operations": list(self.operations),
                "raw_operations_enabled": self.config.raw_operations_enabled,
                "views": ["live", "scratch"],
                "ordinary_receipts": "same_transaction",
                "diagnostics": {
                    "query_plan": {
                        "executed": False,
                        "parameter_values_applied": False,
                        "planning_timeout_enforced": False,
                        "planning_memory_enforced": False,
                        "supported_limits": ["max_input_bytes", "max_output_bytes"],
                    },
                    "query_profile": {
                        "executed": True,
                        "read_only": True,
                        "supported_limits": [
                            "timeout_ms",
                            "max_query_memory_bytes",
                            "max_rows",
                            "max_input_bytes",
                            "max_output_bytes",
                        ],
                    },
                },
            }
        if isinstance(request, m.DBOperationStatusRequest):
            key = (
                RECEIPT_PREFIX + sha256(canonical([self.binding_id, caller, request.operation_id]).encode()).hexdigest()
            )
            prior = self._record(session, key)
            result = json.loads(prior["record"]) if prior else {"state": "unseen"}
            if result.get("state") == "in_progress":
                # This sequential runtime cannot serve status while its request is running.
                result["state"] = "unknown"
            if result.get("load_id"):
                result["applied"] = self.db.bulk_load_applied(result["load_id"])
            return result
        if isinstance(request, m.DBBulkStatusRequest):
            return {"load_id": request.load_id, "applied": self.db.bulk_load_applied(request.load_id)}
        if isinstance(request, m.ListLabelsRequest):
            return {"labels": [n for n in self.db.list_labels() if n != RECEIPT_LABEL]}
        if isinstance(request, m.ListEdgeTypesRequest):
            return {"edge_types": self.db.list_edge_types()}
        if isinstance(request, m.GetLabelInfoRequest):
            return self._label_info(identifier(request.label))
        if isinstance(request, m.GetSchemaRequest):
            return encode(self.db.schema().current())
        if isinstance(request, (m.QueryRequest, m.ExecuteRequest)):
            if not self.config.raw_operations_enabled:
                raise RuntimeFailure(
                    "unsupported_operation", "validate", "Raw operations are disabled on this instance"
                )
            if isinstance(request, m.QueryRequest):
                return self._query(session, request.query, request.params, limits)
            op = m.Operation(
                name="raw_execute",
                kind="mutation",
                parameters_schema={"type": "object"},
                statements=[m.Statement(text=request.query)],
            )
            return self._mutate(session, request, caller, op, limits)
        if isinstance(request, m.VectorSearchRequest):
            return self._vector_search(session, request, limits)
        return self._effect_primitive(session, request, caller)

    def _vector_search(self, session, request, limits):
        identifier(request.label)
        identifier(request.property_name)
        if request.k > limits["max_rows"]:
            raise RuntimeFailure("invalid_parameters", "validate", "Vector k exceeds max_rows")
        info = self.db.get_label_info(request.label)
        prop = next((p for p in info.properties if p.name == request.property_name), None) if info else None
        if not prop or prop.data_type != f"vector:{len(request.vector)}":
            raise RuntimeFailure("invalid_parameters", "validate", "Vector dimension differs from schema")
        query = "CALL uni.vector.query($label, $property, $vector, $k) YIELD vid, distance"
        if request.filter_query:
            query += " WHERE " + request.filter_query
        query += " RETURN vid, distance"
        params = deepcopy(request.filter_params)
        if set(params) & {"label", "property", "vector", "k"}:
            raise RuntimeFailure("invalid_parameters", "validate", "Filter parameters use reserved names")
        params.update(label=request.label, property=request.property_name, vector=request.vector, k=request.k)
        return self._query(session, query, params, limits)

    def _effect_primitive(self, session, request, caller):
        # Validate deterministic arguments before journaling native administration.
        for field in ("label", "edge_type", "property_name"):
            if hasattr(request, field):
                identifier(getattr(request, field))
        if isinstance(request, m.CreateEdgeTypeRequest):
            for label in request.source_labels + request.target_labels:
                identifier(label)
        if isinstance(request, (m.InsertVerticesRequest, m.InsertEdgesRequest)):
            return self._journaled(
                session, request, caller, lambda record, persist: self._bulk(session, request, record, persist)
            )
        return self._journaled(session, request, caller, lambda record, persist: self._admin(request))

    def _label_info(self, name):
        info = self.db.get_label_info(name)
        if info is None:
            raise RuntimeFailure("not_found", "query", "Label does not exist")
        return {
            "name": info.name,
            "count": info.count,
            "properties": [
                {"name": p.name, "type": p.data_type, "nullable": p.nullable, "is_indexed": p.is_indexed}
                for p in info.properties
            ],
            "indexes": [
                {"name": i.name, "type": i.index_type, "properties": i.properties, "status": i.status}
                for i in info.indexes
            ],
        }

    def _admin(self, request):
        if isinstance(request, m.CreateLabelRequest):
            self.db.schema().label(request.label).apply()
            return {"label": request.label}
        if isinstance(request, m.CreateEdgeTypeRequest):
            self.db.schema().edge_type(request.edge_type, request.source_labels, request.target_labels).apply()
            return {"edge_type": request.edge_type}
        if isinstance(request, m.AddPropertyRequest):
            builder = self.db.schema().label(request.label)
            data_type = (
                f"vector:{request.vector_dimension}" if request.vector_dimension else request.property_type.value
            )
            method = builder.property_nullable if request.nullable else builder.property
            method(request.property_name, data_type).apply()
            return {"label": request.label, "property_name": request.property_name}
        if isinstance(request, (m.CreateScalarIndexRequest, m.CreateVectorIndexRequest)):
            config = (
                request.index_type.value
                if isinstance(request, m.CreateScalarIndexRequest)
                else {"type": "vector", "algorithm": "flat", "metric": request.metric.value}
            )
            self.db.schema().label(request.label).index(request.property_name, config).apply()
            return {"label": request.label, "property_name": request.property_name}
        if isinstance(request, m.FlushRequest):
            self.db.flush()
            return {"flushed": True}
        raise RuntimeFailure("unsupported_operation", "validate", "Unknown primitive operation")

    def _bulk(self, session, request, record, persist):
        edges = []
        if isinstance(request, m.InsertEdgesRequest):
            for edge in request.edges:
                rows = session.query(
                    "MATCH (a {ext_id: $source}), (b {ext_id: $target}) RETURN id(a) AS source, id(b) AS target",
                    {"source": edge.source_ext_id, "target": edge.target_ext_id},
                )
                if len(rows) != 1:
                    raise RuntimeFailure("invalid_parameters", "bulk", "Bulk endpoints must exist")
                edges.append((rows[0]["source"], rows[0]["target"], edge.properties))
        with session.tx() as tx:
            writer = tx.bulk_writer().build()
            record["load_id"] = writer.load_id
            persist()
            try:
                vertices = (
                    writer.insert_vertices(request.label, request.vertices)
                    if isinstance(request, m.InsertVerticesRequest)
                    else []
                )
                if isinstance(request, m.InsertEdgesRequest):
                    writer.insert_edges(request.edge_type, edges)
                stats = writer.commit()
                tx.commit()
            except Exception:
                try:
                    writer.abort()
                except Exception:
                    pass  # Preserve the original commit-outcome exception.
                raise
        return {
            "load_id": stats.load_id,
            "applied": self.db.bulk_load_applied(stats.load_id),
            "vertices_inserted": stats.vertices_inserted,
            "edges_inserted": stats.edges_inserted,
            "vertex_ids": encode(vertices),
            "warnings": stats.warnings,
            "indexes_pending": stats.indexes_pending,
            "index_task_ids": stats.index_task_ids,
        }

    def close(self):
        """Explicit owner cleanup; automatic guild shutdown integration is deferred."""
        with self.lock:
            if self.state == "closed":
                return
            self.state = "draining"
            self.db.shutdown()
            self.state = "closed"
