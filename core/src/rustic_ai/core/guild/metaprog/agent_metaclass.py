import ast
import inspect
import logging
import sys
import textwrap
from abc import ABCMeta
from copy import deepcopy
from typing import Any, Callable, Dict, Generic, List, Literal, Optional, Type, get_args

from pydantic import BaseModel

from rustic_ai.core.guild.dsl import AgentSpec, BaseAgentProps
from rustic_ai.core.guild.metaprog.agent_annotations import AgentAnnotations
from rustic_ai.core.guild.metaprog.agent_registry import (
    AgentDependency,
    AgentRegistry,
    HandlerEntry,
    SendMessageCall,
)
from rustic_ai.core.guild.metaprog.constants import MetaclassConstants
from rustic_ai.core.messaging import MessageConstants
from rustic_ai.core.utils.basic_class_utils import (
    get_class_from_name,
    get_qualified_class_name,
)


class MessageHandler:
    def __init__(
        self,
        message_format: type[BaseModel] | Literal["generic_json"],
        handler: Callable,
        handle_essential: bool = False,
    ):
        self.handles_raw = message_format == MessageConstants.RAW_JSON_FORMAT
        self.message_format = message_format
        self.handler = handler
        self.handle_essential = handle_essential


class FormatMessageHandlers:

    def __init__(self):
        self._handlers: Dict[str, Dict[str, MessageHandler]] = {}

    def add_handler(self, handler: Callable):
        message_format = (
            handler.__annotations__[AgentAnnotations.MESSAGE_FORMAT]
            if AgentAnnotations.MESSAGE_FORMAT in handler.__annotations__
            else MessageConstants.RAW_JSON_FORMAT
        )

        handle_essential = (
            handler.__annotations__[AgentAnnotations.HANDLE_ESSENTIAL]
            if AgentAnnotations.HANDLE_ESSENTIAL in handler.__annotations__
            else False
        )

        if isinstance(message_format, type):
            message_format_qname = get_qualified_class_name(message_format)
        else:
            message_format_qname = message_format

        if message_format_qname not in self._handlers:
            self._handlers[message_format_qname] = {}

        self._handlers[message_format_qname][handler.__name__] = MessageHandler(
            message_format, handler, handle_essential
        )

    def get_handlers_for_format(self, message_format: str) -> Dict[str, MessageHandler]:
        handlers = self._handlers.get(message_format)
        if handlers:
            return handlers
        return {}

    def get_essential_handlers_for_format(self, message_format: str) -> Dict[str, MessageHandler]:
        handlers = self.get_handlers_for_format(message_format)
        return {k: v for k, v in handlers.items() if v.handle_essential}


class RawMessageHandlers:

    def __init__(self):
        self._handlers: Dict[str, MessageHandler] = {}

    def add_handler(self, handler: Callable):
        handle_essential = (
            handler.__annotations__[AgentAnnotations.HANDLE_ESSENTIAL]
            if AgentAnnotations.HANDLE_ESSENTIAL in handler.__annotations__
            else False
        )

        self._handlers[handler.__name__] = MessageHandler(MessageConstants.RAW_JSON_FORMAT, handler, handle_essential)

    def get_handlers(self) -> Dict[str, MessageHandler]:
        return self._handlers

    def get_essential_handlers(self) -> Dict[str, MessageHandler]:
        return {k: v for k, v in self._handlers.items() if v.handle_essential}


class HandlerError(Exception):
    """Custom exception for handler registration errors."""

    pass


class AgentMetaclass(ABCMeta):

    DEFAULT_MIXINS = [
        "rustic_ai.core.guild.agent_ext.mixins.state_refresher.StateRefresherMixin",
        "rustic_ai.core.guild.agent_ext.mixins.health.HealthMixin",
        "rustic_ai.core.guild.agent_ext.mixins.telemetry.TelemetryMixin",
    ]

    def __new__(metaclass, name, bases, dct, /, **kwargs):
        if name == "Agent":
            return super().__new__(metaclass, name, bases, dct, **kwargs)
        else:
            bases = MetaclassHelper.extend_with_mixins(bases)
            new_mcls = super().__new__(metaclass, name, bases, dct, **kwargs)
            if bool(new_mcls.__abstractmethods__):  # pragma: no cover
                # This is an abstract class, so do not process it
                return new_mcls

            generic_type = MetaclassHelper.get_generic_type(new_mcls)

            if "__init__" in dct:
                apt = MetaclassHelper.get_agent_param_type(new_mcls, generic_type)
                generic_type = MetaclassHelper.select_generic_type(name, generic_type, apt)

            cls_annotations = deepcopy(getattr(new_mcls, "__annotations__", {}))

            cls_annotations[MetaclassConstants.AGENT_PROPS_TYPE] = generic_type
            setattr(new_mcls, "__annotations__", cls_annotations)

            (
                message_handlers,
                raw_message_handlers,
                before_fixtures,
                after_fixtures,
                on_send_fixtures,
                on_error_fixtures,
                message_mod_fixtures,
            ) = MetaclassHelper.find_handlers(new_mcls)

            setattr(new_mcls, MetaclassConstants.MESSAGE_HANDLERS, message_handlers)
            setattr(new_mcls, MetaclassConstants.RAW_MESSAGE_HANDLERS, raw_message_handlers)
            setattr(new_mcls, MetaclassConstants.BEFORE_FIXTURES, before_fixtures)
            setattr(new_mcls, MetaclassConstants.AFTER_FIXTURES, after_fixtures)
            setattr(new_mcls, MetaclassConstants.ON_SEND_FIXTURES, on_send_fixtures)
            setattr(new_mcls, MetaclassConstants.ON_ERROR_FIXTURES, on_error_fixtures)
            setattr(new_mcls, MetaclassConstants.MESSAGE_MOD_FIXTURES, message_mod_fixtures)

        return new_mcls

    def __init__(cls, name, bases, dct, /, **kwargs):
        super().__init__(name, bases, dct, **kwargs)

        if name != "Agent" and not bool(cls.__abstractmethods__):

            handler_entries: Dict[str, HandlerEntry] = {}
            agent_dependencies: List[AgentDependency] = []

            # Gather send calls and register them
            send_calls = MetaclassHelper.gather_send_calls(cls)

            call_map: dict = {}
            for call in send_calls:
                if call["agent_name"] == f"{cls.__module__}.{cls.__name__}":
                    handler_name = call["handler_name"]
                    if handler_name not in call_map:
                        call_map[handler_name] = []
                    call_map[handler_name].append(
                        SendMessageCall(
                            calling_class=call["function_class_name"],
                            calling_function=call["function_name"],
                            call_type=call["call_type"],
                            message_type=call["message_type"],
                        )
                    )

            for _, method in dct.items():
                if callable(method) and method.__annotations__.get(AgentAnnotations.ISHANDLER):

                    message_format = (
                        method.__annotations__[AgentAnnotations.MESSAGE_FORMAT]
                        if AgentAnnotations.MESSAGE_FORMAT in method.__annotations__
                        else None
                    )

                    message_format_name = (
                        get_qualified_class_name(message_format)
                        if message_format
                        and (isinstance(message_format, type) and issubclass(message_format, BaseModel))
                        else MessageConstants.RAW_JSON_FORMAT
                    )

                    message_format_schema = (
                        message_format.model_json_schema()
                        if message_format
                        and (isinstance(message_format, type) and issubclass(message_format, BaseModel))
                        else {"type": "object"}
                    )

                    message_format_doc = message_format.__doc__ if message_format else ""

                    logging.debug(f"Registering handler {method.__name__} for {message_format_name} in {name}")

                    handler_name = method.__name__
                    handler_entries[handler_name] = HandlerEntry(
                        handler_name=handler_name,
                        message_format=message_format_name,
                        message_format_schema=message_format_schema,
                        handler_doc=message_format_doc,
                        send_message_calls=call_map.get(handler_name, []),
                    )

                    if AgentAnnotations.DEPENDS_ON in method.__annotations__:
                        agent_dependencies.extend(method.__annotations__[AgentAnnotations.DEPENDS_ON])

            agent_doc: str = cls.__doc__ if cls.__doc__ else "No documentation written for Agent"

            # for handler_name, calls in call_map.items():
            #    AgentRegistry.register_send_calls(cls.__name__, handler_name, calls)

            AgentRegistry.register(
                name,
                f"{cls.__module__}.{cls.__name__}",
                agent_doc,
                handler_entries,
                cls.__annotations__[MetaclassConstants.AGENT_PROPS_TYPE],
                agent_dependencies,
            )

            cls.__annotations__[AgentAnnotations.DEPENDS_ON] = agent_dependencies


class MetaclassHelper:
    @staticmethod
    def extend_with_mixins(bases):
        mixins = AgentMetaclass.DEFAULT_MIXINS

        for mixin in mixins:
            try:
                logging.debug(f"Loading Agent Mixin {mixin}")
                mixin_class = get_class_from_name(mixin)
                bases = bases + (mixin_class,)
            except Exception as e:  # pragma: no cover
                logging.debug(f"Error loading Mixin [{mixin}]: {e}")
                continue
        return bases

    @staticmethod
    def select_generic_type(name, generic_type, apt):
        if apt != generic_type:
            if generic_type != BaseAgentProps and apt != BaseAgentProps:  # pragma: no cover
                raise TypeError(
                    f"{name} must implement __init__ with AgentSpec[{generic_type.__name__}] or inherit Agent[{apt.__name__}]"
                )

            if generic_type == BaseAgentProps:
                generic_type = apt
        return generic_type

    @staticmethod
    def get_agent_param_type(new_mcls, generic_type):

        name = new_mcls.__name__

        def is_init_method(m):
            return inspect.isfunction(m) and m.__name__ == "__init__"

        init_method = inspect.getmembers(new_mcls, predicate=is_init_method)[0][1]

        sig = inspect.signature(init_method)
        sig_params = sig.parameters
        param_names = [p.name for p in sig_params.values()]
        if param_names != ["self", "agent_spec"]:  # pragma: no cover
            raise TypeError(f"{name} must implement __init__ exactly as defined in base Agent")

        agent_spec_type: Type[AgentSpec] = sig_params["agent_spec"].annotation

        if agent_spec_type != inspect._empty:
            apt = agent_spec_type.get_pydantic_generic_type()
        else:
            apt = generic_type
        return apt

    @staticmethod
    def get_generic_type(new_mcls):
        name = new_mcls.__name__
        generic_type = BaseAgentProps
        if hasattr(new_mcls, "__orig_bases__"):
            base0 = new_mcls.__orig_bases__[0]

            if hasattr(base0, "__origin__") and base0.__origin__.__name__ == "Agent":
                base_arg = get_args(base0)
                if len(base_arg) >= 1:
                    baps: Type = base_arg[0]
                    if issubclass(baps, BaseAgentProps):
                        generic_type = base_arg[0]
            elif not hasattr(base0, "__origin__") or base0.__origin__ != Generic:  # pragma: no cover
                raise TypeError(f"{name} must inherit from Agent with a BaseAgentProps generic type")
        return generic_type

    @staticmethod
    def find_handlers(new_mcls):
        message_handlers: FormatMessageHandlers = FormatMessageHandlers()
        raw_message_handlers: RawMessageHandlers = RawMessageHandlers()
        before_fixtures: List[Callable] = []
        after_fixtures: List[Callable] = []
        on_send_fixtures: List[Callable] = []
        on_error_fixtures: List[Callable] = []
        message_mod_fixtures: List[Callable] = []

        dct = inspect.getmembers(new_mcls, predicate=inspect.isfunction)

        for name, method in dct:
            if callable(method):
                if method.__annotations__.get(AgentAnnotations.ISHANDLER):
                    message_format = (
                        method.__annotations__[AgentAnnotations.MESSAGE_FORMAT]
                        if AgentAnnotations.MESSAGE_FORMAT in method.__annotations__
                        else None
                    )

                    message_format_name = (
                        get_qualified_class_name(message_format) if message_format else MessageConstants.RAW_JSON_FORMAT
                    )

                    logging.debug(f"Found handler {method.__name__} for {message_format_name} in {new_mcls.__name__}")

                    if method.__annotations__.get(AgentAnnotations.HANDLES_RAW):
                        raw_message_handlers.add_handler(method)
                    else:
                        message_handlers.add_handler(method)

                elif method.__annotations__.get(AgentAnnotations.IS_BEFORE_PROCESS_FIXTURE):
                    before_fixtures.append(method)
                elif method.__annotations__.get(AgentAnnotations.IS_AFTER_PROCESS_FIXTURE):
                    after_fixtures.append(method)
                elif method.__annotations__.get(AgentAnnotations.IS_ON_SEND_FIXTURE):
                    on_send_fixtures.append(method)
                elif method.__annotations__.get(AgentAnnotations.IS_ON_SEND_ERROR_FIXTURE):
                    on_error_fixtures.append(method)
                elif method.__annotations__.get(AgentAnnotations.IS_MESSAGE_MOD_FIXTURE):
                    message_mod_fixtures.append(method)
        return (
            message_handlers,
            raw_message_handlers,
            before_fixtures,
            after_fixtures,
            on_send_fixtures,
            on_error_fixtures,
            message_mod_fixtures,
        )

    @staticmethod
    def gather_send_calls(cls):
        logging.debug(f"Analyzing class {cls.__name__} for send calls")
        try:
            module_source = inspect.getsource(sys.modules[cls.__module__])
            dedented_code = textwrap.dedent(module_source)
            module_tree = ast.parse(dedented_code)
        except Exception as e:
            logging.debug(f"Error parsing module source: {e}")
            return []

        visitor = AgentCodeAnalyzer(cls, module_tree, cls.__module__)
        visitor.visit(module_tree)
        return visitor.calls_found


class AgentCodeAnalyzer(ast.NodeVisitor):
    def __init__(
        self,
        cls: Any,
        module_tree: ast.Module,
        module_name: str,
        parsing_nested_call: bool = False,
        agent_name: Optional[str] = None,
        handler_name: Optional[str] = None,
        context_param: Optional[str] = None,
        current_class: Optional[str] = None,
        imports: dict = {},
        classes: dict = {},
        cache: dict = {},
        global_scope: dict = {},
        class_function_nodes: Dict[str, ast.AST] = {},
    ):
        logging.debug(f"Creating FunctionCallVisitor for {cls.__name__}")
        self.cls = cls
        self.module_name = module_name
        self.calls_found: list = []
        self.imports = imports
        self.classes = classes
        self.agent_name = agent_name
        self.handler_name = handler_name
        self.current_class = current_class
        self.current_function = None
        self.current_fn_is_handler = False
        self.tracked_functions = ["send", "send_dict", "send_error"]
        self.context_param = context_param
        self.cache = cache
        self.nested_calls_found: dict = {}
        self.global_scope = global_scope or {**globals(), **locals()}
        self.parsing_nested_call = parsing_nested_call
        self.class_function_nodes = class_function_nodes

        self.nested_calls_to_analyze: dict = {}
        self.variable_assignments: dict = {}
        self.module_tree = module_tree

    def visit_Import(self, node):
        for alias in node.names:
            self.imports[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.imports[alias.asname or alias.name] = full_name
        self.generic_visit(node)

    def visit_Assign(self, node):
        # Track simple variable assignments
        if isinstance(node.targets[0], ast.Name):
            var_name = node.targets[0].id
            self.variable_assignments[var_name] = node.value
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.current_class = node.name
        self.classes[node.name] = f"{self.module_name}.{node.name}" if self.module_name else node.name
        self.generic_visit(node)

        nested_calls = self.nested_calls_to_analyze
        for handler_name, methods in nested_calls.items():
            unique_methods = {method_name: param_context for method_name, param_context in methods}
            for method_name, param_context in unique_methods.items():
                nested_calls = self._visit_method(handler_name, method_name, param_context)
                self.calls_found.extend(nested_calls)

        self.current_class = None

    def visit_FunctionDef(self, node):
        self.current_function = node.name
        if self.current_function and self.current_function not in self.class_function_nodes:
            self.class_function_nodes[self.current_function] = node  # type: ignore
        self.current_fn_is_handler = False
        if (
            node.decorator_list
            and isinstance(node.decorator_list[0], ast.Call)
            and node.decorator_list[0].func
            and (
                (hasattr(node.decorator_list[0].func, "id") and node.decorator_list[0].func.id == "processor")
                or (hasattr(node.decorator_list[0].func, "attr") and node.decorator_list[0].func.attr == "processor")
            )
        ):
            self.current_fn_is_handler = True
            self.context_param = node.args.args[1].arg
            self.handler_name = self.current_function
            if not self.agent_name:
                self.agent_name = f"{self.cls.__module__}.{self.cls.__name__}"

            self.generic_visit(node)

            nested_calls = self.nested_calls_found.get(self.current_function, {})
            for nested_fn, calls in nested_calls.items():
                self.calls_found.extend(calls)
        elif self.parsing_nested_call:
            self.generic_visit(node)

        self.current_function = None
        self.current_fn_is_handler = False
        self.context_param = None

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            ctx = getattr(node.func.value, "id", None)
            if node.func.attr in self.tracked_functions and ctx == self.context_param:
                message_type = self._get_message_type(node)
                self.calls_found.append(
                    {
                        "agent_name": self.agent_name,
                        "handler_name": self.handler_name,
                        "function_class_name": self.current_class,
                        "function_name": self.current_function,
                        "is_handler": self.current_fn_is_handler,
                        "message_type": message_type,
                        "call_type": node.func.attr,
                    }
                )

        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            ctx_passed_as_kwarg = any(
                isinstance(kw.value, ast.Name) and kw.value.id == self.context_param for kw in node.keywords
            )
            ctx_passed_as_arg = any(isinstance(arg, ast.Name) and arg.id == self.context_param for arg in node.args)

            if ctx_passed_as_kwarg or ctx_passed_as_arg:
                method_name = node.func.attr
                logging.debug(f"Context passed to method {method_name} called from {self.current_function}")
                if node.func.value.id == "self" and self.cls:
                    method = getattr(self.cls, method_name, None)
                    if method:
                        if self.handler_name not in self.nested_calls_to_analyze:
                            self.nested_calls_to_analyze[self.handler_name] = []
                        self.nested_calls_to_analyze[self.handler_name].append((method_name, self.context_param))
                else:
                    self._analyze_nested_function(node.func)

        self.generic_visit(node)

    def _analyze_nested_function(self, func):
        if isinstance(func, ast.Name):
            function_name = func.id
            if function_name in self.global_scope:
                nested_func = self.global_scope[function_name]
                if callable(nested_func):
                    nested_calls = self._analyze_callable(nested_func, function_name, "")
                    self.cache[function_name] = nested_calls
                    self._merge_nested_calls(self.handler_name, function_name, nested_calls)

        elif isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                obj_name = func.value.id
                method_name = func.attr

                if obj_name == "self" and self.cls:
                    nested_func = getattr(self.cls, method_name, None)
                    if callable(nested_func):
                        nested_calls = self._analyze_callable(nested_func, method_name, self.cls.__module__)
                        self.cache[method_name] = nested_calls
                        self._merge_nested_calls(self.handler_name, method_name, nested_calls)
                else:
                    obj = self.global_scope.get(obj_name, None) or getattr(self.cls, obj_name, None)
                    if obj is not None:
                        nested_func = getattr(obj, method_name, None)
                        if callable(nested_func):
                            nested_calls = self._analyze_callable(nested_func, method_name, obj.__module__)
                            self.cache[method_name] = nested_calls
                            self._merge_nested_calls(self.handler_name, method_name, nested_calls)

    def _visit_method(self, handler_name, method_name, context_param):
        try:
            method_tree: ast.AST = self.class_function_nodes.get(method_name)  # type: ignore
            new_visitor = AgentCodeAnalyzer(
                self.cls,
                self.module_tree,
                self.module_name,
                True,
                self.agent_name,
                handler_name,
                context_param,
                self.current_class,
                self.imports,
                self.classes,
                self.cache,
                self.global_scope,
                self.class_function_nodes,
            )
            new_visitor.visit(method_tree)
            return new_visitor.calls_found
        except Exception as e:
            logging.debug(f"Error analyzing method {method_name}: {e}")
            return {}

    def _merge_nested_calls(self, handler_name, method_name, nested_calls):
        if nested_calls:
            if method_name not in self.nested_calls_found:
                self.nested_calls_found[handler_name] = {}
            self.nested_calls_found[handler_name][method_name] = nested_calls

    def _analyze_callable(self, nested_func, function_name, function_module):
        try:
            nested_source_code = inspect.getsource(nested_func)
            dedented_code = textwrap.dedent(nested_source_code)
            nested_tree = ast.parse(dedented_code)
            nested_visitor = AgentCodeAnalyzer(self.cls, self.module_tree, function_module)
            nested_visitor.visit(nested_tree)
            return nested_visitor.calls_found
        except Exception as e:
            logging.debug(f"Error analyzing callable {function_name}: {e}")
            return {}

    def _get_message_type(self, node):
        if node.func.attr in ["send", "send_error"]:
            if len(node.args) >= 1:
                return self._resolve_type(node.args[0])
            for kw in node.keywords:
                if kw.arg == "payload":
                    return self._resolve_type(kw.value)
        elif node.func.attr == "send_dict":
            for kw in node.keywords:
                if kw.arg == "format":
                    return self._resolve_type(kw.value)
            if len(node.args) > 2:
                return self._resolve_type(node.args[2])
        return None

    def _resolve_type(self, node):
        if isinstance(node, ast.Constant):  # Python 3.8+
            return repr(node.value)

        elif isinstance(node, ast.Name):
            # Direct reference to a type or variable
            var_name = node.id
            if var_name in self.variable_assignments:
                return self._resolve_type(self.variable_assignments[var_name])

            # If the class is defined in this module, return the fully qualified name
            if var_name in self.classes:
                return self.classes[var_name]

            resolved_name = self.imports.get(node.id, node.id)
            return resolved_name

        elif isinstance(node, ast.Attribute):
            # Handle nested attributes like "module.Class"
            value = node.value
            if isinstance(value, ast.Name):
                base_name = self.imports.get(value.id, value.id)
                return self._get_return_type_annotation(base_name, node.attr, self.cls)

            elif isinstance(value, ast.Attribute):
                return self._resolve_type(value) + f".{node.attr}"

        elif isinstance(node, ast.Call):
            # Handle class instantiations like "ClassName(...)"
            if isinstance(node.func, ast.Name):
                if node.func.id in self.classes:
                    return self.classes[node.func.id]

                return self.imports.get(node.func.id, node.func.id)
            elif isinstance(node.func, ast.Attribute):
                method_type = self._resolve_type(node.func)
                if method_type:
                    return self._infer_return_type(method_type, node)

        return None  # Fallback if we can't resolve the type

    def _infer_return_type(self, method_type, call_node):
        # Try to find the method definition in the AST
        for class_node in self.module_tree.body:
            if isinstance(class_node, ast.ClassDef):
                for method in class_node.body:
                    if isinstance(method, ast.FunctionDef) and method.name == method_type.split(".")[-1]:
                        return self._infer_type_from_return_statements(method)
        # If the method definition isn't found, fallback to the raw method_type
        return method_type

    def _infer_type_from_return_statements(self, method_node):
        for stmt in method_node.body:
            if isinstance(stmt, ast.Return):
                return self._resolve_type(stmt.value)
        return None

    def _get_return_type_annotation(self, class_name, method_name, cls):
        """Retrieve the return type annotation for a given method, if available."""
        try:
            clz = get_class_from_name(class_name)
            method: Callable = getattr(clz, method_name, None)  # type: ignore
            # Retrieve the signature of the method
            signature = inspect.signature(method)
            # Return the annotation of the return type
            return_type = (
                signature.return_annotation if signature.return_annotation != inspect.Signature.empty else class_name
            )
            if return_type in self.imports:
                return self.imports[return_type]
            return return_type
        except Exception as e:
            logging.debug(f"Could not retrieve return type for {class_name}.{method_name}: {e}")
            return class_name
