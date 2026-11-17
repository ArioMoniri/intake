"""The pgvector column type, without the pgvector Python package (INT-123).

One column in the schema holds a vector, and the operations on it — the
distance ordering and the dimension check — are spelled in SQL by the one
store that runs them (:mod:`intake_platform.records.index_store`) and by the
migration. So the type needs to do two things only: name itself ``vector`` in
DDL, and carry a sequence of floats across the driver as pgvector's text form
``[x,y,…]``. That is not worth a new dependency and its licence review.

The column is declared **without** a dimension: no embedding model is pinned
(files/03 §4.9.1 has no row for one), so there is no number to declare, and the
migration's ``CHECK (vector_dims(embedding) = dimensions)`` binds each row to
the dimension its own model declared instead. Every read is an exact scan of
one patient's namespace (RLS, 0014), which is a few hundred rows — an
approximate index would trade recall for a speed nobody needs here.

On SQLite (the unit lane) ``vector`` is just a declared type name and the value
is stored as its text form, which is all the erasure contract needs.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.engine import Dialect
from sqlalchemy.types import UserDefinedType

__all__ = ["Vector", "parse_vector", "vector_literal"]


def vector_literal(values: Sequence[float]) -> str:
    """pgvector's text form. Refuses an empty or non-finite vector, which the
    server would also refuse — but with the value in its error message."""
    floats = [float(value) for value in values]
    if not floats:
        raise ValueError("a vector has at least one dimension")
    if not all(math.isfinite(value) for value in floats):
        raise ValueError("a vector component must be finite")
    return "[" + ",".join(repr(value) for value in floats) + "]"


def parse_vector(text: str) -> tuple[float, ...]:
    """The inverse of :func:`vector_literal`."""
    body = text.strip()
    if not (body.startswith("[") and body.endswith("]")):
        raise ValueError("not a vector literal")
    return tuple(float(part) for part in body[1:-1].split(",") if part.strip())


class Vector(UserDefinedType[tuple[float, ...]]):
    """``vector`` — dimensionless in DDL; see the module docstring for why."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "VECTOR"

    def bind_processor(self, dialect: Dialect) -> Callable[[Any], str | None]:
        def process(value: Any) -> str | None:
            return None if value is None else vector_literal(value)

        return process

    def result_processor(
        self, dialect: Dialect, coltype: object
    ) -> Callable[[Any], tuple[float, ...] | None]:
        def process(value: Any) -> tuple[float, ...] | None:
            return None if value is None else parse_vector(str(value))

        return process
