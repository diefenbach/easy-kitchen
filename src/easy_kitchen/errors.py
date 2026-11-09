"""Transport-independent errors exposed by web, REST and MCP services."""


class ServiceError(ValueError):
    code = "invalid_input"

    def __init__(self, message, *, field=None):
        super().__init__(str(message))
        self.field = field

    def as_dict(self):
        data = {"code": self.code, "message": str(self)}
        if self.field:
            data["field"] = self.field
        return data


class ObjectNotFoundError(ServiceError):
    code = "not_found"


class SelectionMismatchError(ServiceError):
    code = "selection_mismatch"


class QuantityOverflowError(ServiceError):
    code = "quantity_overflow"

    def __init__(self, message):
        super().__init__(message, field="quantity")
