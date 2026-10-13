"""Pure C1/C1.1 codec: logical keys in, physical keys out, no SDK imports."""
from collections.abc import Mapping, Sequence
import json
from typing import Any


class BuilderContractError(ValueError):
    """A property violates the project schema contract."""


def canonical_json(value: Any) -> str:
    """Preserve Unicode and list order; sort dictionary keys only."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _validate_value(name: str, value: Any, kind: str, *, decoded: bool = False) -> None:
    if kind in ('TEXT', 'OPTIONAL_TEXT'):
        valid, expected = isinstance(value, str), 'str'
    elif kind in ('INTEGER', 'OPTIONAL_INTEGER'):
        valid, expected = type(value) is int, 'native int excluding bool'
    elif kind == 'BOOLEAN_ENCODING':
        valid = (type(value) is str and value in ('true', 'false')) if decoded else type(value) is bool
        expected = "lowercase Text true/false" if decoded else 'bool'
    elif kind == 'JSON_TEXT':
        try:
            canonical_json(value)
        except (TypeError, ValueError) as exc:
            raise BuilderContractError(f'{name}: invalid JSON value: {exc}') from exc
        return
    else:
        raise BuilderContractError(f'{name}: unknown contract type {kind!r}')
    if not valid:
        raise BuilderContractError(f'{name}: expected {expected}, got {type(value).__name__}')
    if name in ('id', 'name') and not value.strip():
        raise BuilderContractError(f'{name}: blank identity/name')


def validate_properties(
    values: Mapping[str, Any], property_contract: Sequence[Mapping[str, Any]],
    unit_types: Sequence[str] = (),
) -> None:
    """Validate logical values; required/optional flags come from contract rows."""
    for prop in property_contract:
        name = prop['logical_name']
        value = values.get(name)
        if value is None:
            if prop['required']:
                raise BuilderContractError(f'{name}: required property missing/null')
            continue
        _validate_value(name, value, prop['contract_type'])
        if name == 'unit_type' and unit_types and value not in unit_types:
            raise BuilderContractError(f'{name}: invalid enum {value!r}')


def encode_properties(
    values: Mapping[str, Any], property_contract: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Encode logical Python JSON values exactly once; Integer stays native."""
    validate_properties(values, property_contract)
    result = {}
    for prop in property_contract:
        value = values.get(prop['logical_name'])
        if value is None:
            continue
        kind = prop['contract_type']
        if kind == 'JSON_TEXT':
            value = canonical_json(value)
        elif kind == 'BOOLEAN_ENCODING':
            value = 'true' if value else 'false'
        result[prop['schema_name']] = value
    return result


def decode_properties(
    raw: Mapping[str, Any], property_contract: Sequence[Mapping[str, Any]],
    *, server_encoded: bool = False,
) -> dict[str, Any]:
    """Return logical keys and semantic JSON; Boolean encoding remains Text.

    server_encoded explicitly requests the server's outer JSON layer for
    non-identity properties. No guessing or numeric Text coercion occurs.
    """
    result = {}
    for prop in property_contract:
        name, physical = prop['logical_name'], prop['schema_name']
        value = raw.get(physical)
        if value is None:
            if prop['required']:
                raise BuilderContractError(f'{name}: required property missing/null')
            continue
        try:
            if server_encoded and name not in ('id', 'name'):
                if not isinstance(value, str):
                    raise BuilderContractError(f'{name}: outer JSON property must be str')
                value = json.loads(value)
            if value is None:
                if prop['required']:
                    raise BuilderContractError(f'{name}: required property null')
                continue
            if prop['contract_type'] == 'JSON_TEXT':
                if not isinstance(value, str):
                    raise BuilderContractError(f'{name}: JSON_TEXT physical value must be str')
                value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise BuilderContractError(f'{name}: malformed JSON: {exc.msg}') from exc
        _validate_value(name, value, prop['contract_type'], decoded=True)
        result[name] = value
    return result
