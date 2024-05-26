import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Union, Optional
import typing
from uuid import UUID

from django.utils.functional import Promise
from pydantic import IPvAnyAddress, Json
from pydantic.fields import FieldInfo
from pydantic.v1.fields import Required
from pydantic_core import PydanticUndefined

try:
    from django.db.models.fields import NOT_PROVIDED
except ImportError:

    class NOT_PROVIDED:
        pass


logger = logging.getLogger("djantic")


INT_TYPES = [
    "AutoField",
    "BigAutoField",
    "IntegerField",
    "SmallIntegerField",
    "BigIntegerField",
    "PositiveIntegerField",
    "PositiveSmallIntegerField",
]

STR_TYPES = [
    "CharField",
    "EmailField",
    "URLField",
    "SlugField",
    "TextField",
    "FilePathField",
    "FileField",
]


FIELD_TYPES = {
    "GenericIPAddressField": IPvAnyAddress,
    "BooleanField": bool,
    "BinaryField": bytes,
    "DateField": date,
    "DateTimeField": datetime,
    "DurationField": timedelta,
    "TimeField": time,
    "DecimalField": Decimal,
    "FloatField": float,
    "UUIDField": UUID,
    "JSONField": Union[Json, dict, list],  # TODO: Configure this using default
    "ArrayField": List,
    # "IntegerRangeField",
    # "BigIntegerRangeField",
    # "CICharField",
    # "CIEmailField",
    # "CIText",
    # "CITextField",
    # "DateRangeField",
    # "DateTimeRangeField",
    # "DecimalRangeField",
    # "FloatRangeField",
    # "HStoreField",
    # "RangeBoundary",
    # "RangeField",
    # "RangeOperators",
}


def get_internal_type(field):
    python_type = None
    internal_type = field.get_internal_type()
    if internal_type in STR_TYPES:
        python_type = str

    elif internal_type in INT_TYPES:
        python_type = int

    elif internal_type in FIELD_TYPES:
        python_type = FIELD_TYPES[internal_type]

    else:  # pragma: nocover
        for field_class in type(field).__mro__:
            get_internal_type = getattr(field_class, "get_internal_type", None)
            if get_internal_type:
                _internal_type = get_internal_type(field_class())
                if _internal_type in FIELD_TYPES:
                    python_type = FIELD_TYPES[_internal_type]
                    break
    return python_type


def ModelSchemaField(field: Any, schema_name: str) -> tuple:
    default = Required
    default_factory = None
    description = None
    title = None
    max_length = None

    try:
        deconstructed = field.deconstruct()
        field_options = deconstructed[3] or {}
        blank = field_options.pop("blank", False)
        null = field_options.pop("null", False)
    except AttributeError:
        # Field does not have `deconstruct` method, just default to false
        blank = False
        null = False

    if field.is_relation:
        if not field.related_model:
            internal_type = field.model._meta.pk.get_internal_type()
        else:
            internal_type = field.related_model._meta.pk.get_internal_type()
            if not field.concrete and field.auto_created or field.null:
                default = None

        pk_type = FIELD_TYPES.get(internal_type, int)
        if field.one_to_many or field.many_to_many:
            python_type = List[Dict[str, pk_type]]
        else:
            python_type = pk_type

        if blank or null:
            python_type = Union[python_type, None]

    else:
        if field.choices:
            enum_choices = {}
            for k, v in field.choices:
                if Promise in type(v).__mro__:
                    v = str(v)
                enum_choices[v] = k
            if field.blank:
                enum_choices["_blank"] = ""

            enum_prefix = (
                f"{schema_name.replace('_', '')}{field.name.title().replace('_', '')}"
            )
            python_type = Enum(  # type: ignore
                f"{enum_prefix}Enum",
                enum_choices,
                module=__name__,
            )

            if field.has_default() and isinstance(field.default, Enum):
                default = field.default.value
        else:
            python_type = get_internal_type(field)
            if field.get_internal_type() == "ArrayField":
                python_type = List[get_internal_type(field.base_field)]

        if python_type is None:
            logger.warning(
                "%s is currently unhandled, defaulting to str.", field.__class__
            )
            python_type = str

        if default is Required and field.has_default():
            if callable(field.default):
                default_factory = field.default
                default = PydanticUndefined
            else:
                default = field.default
        elif field.primary_key or blank or null:
            default = None
            python_type = Union[python_type, None]

        if (default is not None or NOT_PROVIDED) and field.null:
            python_type = Union[python_type, None]

        description = field.help_text
        title = field.verbose_name.title()

    if not description:
        related_field_name = None
        if field.related_model:
            related_field_name = field.target_field.name

        description = related_field_name or field.name

    if (
        getattr(field, "get_internal_type", lambda: None)() in STR_TYPES
        and not field.choices
    ):
        max_length = field.max_length

    field_info = FieldInfo(
        default=default,
        default_factory=default_factory,
        title=title,
        description=str(description),
        max_length=max_length,
    )

    field_is_optional = all([
        getattr(field, "null", None),
        field.is_relation,
        # A list that is null, is the empty list. So there is no need
        # to make it nullable.
        typing.get_origin(python_type) is not list
    ])
    if field_is_optional:
        python_type = Optional[python_type]

    return (
        python_type,
        field_info
    )
