import importlib


def get_class_from_name(full_class_name: str) -> type:
    # Split the full class name into module and class parts
    module_name, class_name = full_class_name.rsplit(".", 1)

    # Dynamically import the module and get the class
    module = importlib.import_module(module_name)
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise TypeError(f"Class {class_name} not found in module {module_name}")


def get_qualified_class_name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__name__}"
