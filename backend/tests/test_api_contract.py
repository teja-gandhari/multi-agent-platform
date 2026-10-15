
from app.main import app


def test_required_api_routes_exist():
    schema = app.openapi()
    paths = schema["paths"]

    required_routes = {
        "/health": {"get"},
        "/project": {"get", "post"},
        "/agents/run": {"post"},
    }

    for path, methods in required_routes.items():
        assert path in paths, f"Missing API route: {path}"

        available_methods = {
            method.lower()
            for method in paths[path]
            if method.lower() in {
                "get", "post", "put", "patch", "delete"
            }
        }

        assert methods.issubset(available_methods), (
            f"Missing methods for {path}: "
            f"{methods - available_methods}"
        )


def test_protected_routes_require_authentication():
    schema = app.openapi()
    paths = schema["paths"]

    protected_operations = [
        ("/project", "get"),
        ("/project", "post"),
        ("/agents/run", "post"),
    ]

    for path, method in protected_operations:
        operation = paths[path][method]
        assert operation.get("security"), (
            f"{method.upper()} {path} has no declared "
            "authentication requirement"
        )

