"""Input validation. Every function raises ValidationError and never touches the database."""
import math
import re
from datetime import datetime

from .enums import (DECISION_ACTIONS, EVIDENCE_STATUSES, FIELD_KEYS, FIELD_SOURCES,
                    REL_TYPES, SCREENSHOT_TYPES)
from .errors import ValidationError

_HEX = re.compile(r"^[0-9a-f]+$")


def require_str(name, value, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def hex_string(name, value, length=None, allow_none=False):
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not _HEX.match(value):
        raise ValidationError(f"{name} must be a lowercase hex string")
    if length is not None and len(value) != length:
        raise ValidationError(f"{name} must be {length} hex characters")
    return value


def timestamp(name, value):
    """ISO-8601 with an explicit UTC offset (or 'Z'). Naive timestamps are rejected."""
    require_str(name, value)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError(f"{name} must be an ISO-8601 timestamp, got {value!r}")
    if dt.tzinfo is None:
        raise ValidationError(f"{name} must include a UTC offset, got {value!r}")
    return value


def unit_float(name, value, allow_none=False):
    """0..1 inclusive. Always returns a float so int 1 and float 1.0 hash identically."""
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a number between 0 and 1")
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        raise ValidationError(f"{name} must be between 0 and 1, got {value!r}")
    return float(value)


def choice(name, value, allowed):
    if value not in allowed:
        raise ValidationError(f"{name} must be one of {list(allowed)}, got {value!r}")
    return value


def evidence_status(value):
    return choice("status", value, EVIDENCE_STATUSES)


def _field_value(key, v):
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValidationError(f"fields[{key}] must be string, number or null")
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        raise ValidationError(f"fields[{key}] must be finite")
    return v


def interpretation_fields(fields, field_confidence, field_source):
    """Normalise to the full 16-key contract. A null is correct; an invented value is a bug.

    Rules: unknown keys rejected; missing keys become null/0.0; a null field must have
    confidence 0; a present field needs confidence > 0 and a known source.
    """
    if not isinstance(fields, dict) or not isinstance(field_confidence, dict):
        raise ValidationError("fields and field_confidence must be objects")
    field_source = field_source or {}
    if not isinstance(field_source, dict):
        raise ValidationError("field_source must be an object")
    for name, d in (("fields", fields), ("field_confidence", field_confidence), ("field_source", field_source)):
        extra = set(d) - set(FIELD_KEYS)
        if extra:
            raise ValidationError(f"{name} has unknown keys: {sorted(extra)}")
    out_f, out_c, out_s = {}, {}, {}
    for k in FIELD_KEYS:
        v = _field_value(k, fields.get(k))
        if v is None:
            c = field_confidence.get(k, 0.0)
            c = unit_float(f"field_confidence[{k}]", c)
            if c != 0.0:
                raise ValidationError(f"field {k!r} is null but has confidence {c}; null must have confidence 0")
            out_f[k], out_c[k], out_s[k] = None, 0.0, None
        else:
            if k not in field_confidence:
                raise ValidationError(f"field {k!r} has a value but no confidence")
            c = unit_float(f"field_confidence[{k}]", field_confidence[k])
            if c == 0.0:
                raise ValidationError(f"field {k!r} has a value but confidence 0; return null instead")
            s = field_source.get(k)
            if s not in FIELD_SOURCES:
                raise ValidationError(f"field {k!r} needs a source in {list(FIELD_SOURCES)}, got {s!r}")
            out_f[k], out_c[k], out_s[k] = v, c, s
    return out_f, out_c, out_s


def screenshot_type(value):
    return choice("screenshot_type", value, SCREENSHOT_TYPES)


def rel_type(value):
    return choice("type", value, REL_TYPES)


def decision_action(value):
    return choice("action", value, DECISION_ACTIONS)


def basis_list(basis):
    if not isinstance(basis, (list, tuple)):
        raise ValidationError("basis must be a list")
    out = []
    for b in basis:
        if isinstance(b, str) and b.strip():
            out.append(b)
        elif isinstance(b, dict) and b and all(isinstance(k, str) for k in b):
            out.append(b)
        else:
            raise ValidationError("basis entries must be non-empty strings or objects with string keys")
    return out
