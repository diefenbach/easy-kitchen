"""Transport-independent errors exposed by web, REST and MCP services."""


class ServiceError(ValueError):
    """A business rule violation, shared by the web UI, the REST API, and MCP.

    `code` is a stable machine-readable reason; `field` names the input that caused it, when there
    is one.
    """

    code = "invalid_input"

    def __init__(self, message, *, field=None):
        super().__init__(str(message))
        self.field = field

    def as_dict(self):
        """Return the error as JSON-ready data: code, message, and field when set."""
        data = {"code": self.code, "message": str(self)}
        if self.field:
            data["field"] = self.field
        return data


class ObjectNotFoundError(ServiceError):
    """The object does not exist or does not belong to the user; the API answers 404."""

    code = "not_found"


class SelectionMismatchError(ServiceError):
    """An id and a name were both given but identify different objects."""

    code = "selection_mismatch"


class QuantityOverflowError(ServiceError):
    """Merging quantities would exceed the quantity field's length."""

    code = "quantity_overflow"

    def __init__(self, message):
        super().__init__(message, field="quantity")
