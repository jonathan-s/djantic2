import inspect
import sys
from enum import Enum
from functools import reduce
from itertools import chain
from typing import Any, Dict, List, Optional, Union, no_type_check

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Manager, Model
from django.db.models.fields.files import ImageFieldFile
from django.db.models.fields.reverse_related import ForeignObjectRel, OneToOneRel
from django.utils.encoding import force_str
from django.utils.functional import Promise
from pydantic import BaseModel, create_model
from pydantic._internal._model_construction import ModelMetaclass
from pydantic.errors import PydanticUserError
from typing_extensions import get_args, get_origin

if sys.version_info >= (3, 10):
    from types import UnionType
else:
    from typing import Union as UnionType

from typing import Generic, TypeVar

from django.db.models import Model as DjangoModel

from .fields import ModelSchemaField

_is_base_model_class_defined = False

_M = TypeVar("_M", bound=DjangoModel)


class ModelSchemaJSONEncoder(DjangoJSONEncoder):
    @no_type_check
    def default(self, obj):  # pragma: nocover
        if isinstance(obj, Promise):
            return force_str(obj)

        return super().default(obj)


def get_field_name(field) -> str:
    if issubclass(field.__class__, ForeignObjectRel) and not issubclass(
        field.__class__, OneToOneRel
    ):
        return getattr(field, "related_name", None) or f"{field.name}_set"
    else:
        return getattr(field, "name", field)


class ModelSchemaMetaclass(ModelMetaclass):
    @no_type_check
    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        for base in reversed(bases):
            if (
                _is_base_model_class_defined
                and issubclass(base, ModelSchema)
                and (
                    ## Start to ensure generic origin is ModelSchema
                    # When schema is inherited from another class with generic
                    # origin, we need to check if the base class is ModelSchema
                    (
                        hasattr(base, "__pydantic_generic_metadata__")
                        and base.__pydantic_generic_metadata__.get("origin")
                        == ModelSchema
                    )
                    or base == ModelSchema
                )
            ):
                config = namespace.get("model_config", None)
                if config == {}:
                    continue

                ## Finish to ensure generic origin is ModelSchema

                include = config.get("include", None)
                exclude = config.get("exclude", None)

                if include and exclude:
                    raise PydanticUserError(
                        "Only one of 'include' or 'exclude' should be set in "
                        "configuration.",
                        code="include-exclude-mutually-exclusive",
                    )

                annotations = namespace.get("__annotations__", {})

                try:
                    ## Get from generic metadata if available
                    #
                    if "model" not in config:
                        if hasattr(
                            base, "__pydantic_generic_metadata__"
                        ) and base.__pydantic_generic_metadata__.get("args"):
                            config["model"] = base.__pydantic_generic_metadata__.get(
                                "args"
                            )[0]

                    fields = config["model"]._meta.get_fields()
                except (AttributeError, KeyError) as exc:
                    raise PydanticUserError(
                        (
                            f'{exc} (Is model_config["model"] a valid Django model class?) '
                            '\nPlease set the model_config["model"] or a generic type with a '
                            "Django model class as the first argument. \n\n"
                            "Example: \n\n"
                            "- class MyModelSchema(ModelSchema):\n"
                            '\n      model_config = {"model": MyModel}\n\n'
                            "or\n\n"
                            "- class MyModelSchema(ModelSchema[MyModel]):\n"
                            "    ...\n"
                        ),
                        code="class-not-valid",
                    ) from None

                if include == "__annotations__":
                    include = list(annotations.keys())
                    cls.model_config["include"] = include
                elif include is None and exclude is None:
                    include = list(annotations.keys()) + [
                        get_field_name(f) for f in fields
                    ]
                    cls.model_config["include"] = include

                field_values = {}
                _seen = set()

                for field in chain(fields, annotations.copy()):
                    field_name = get_field_name(field)

                    if (
                        field_name in _seen
                        or (include and field_name not in include)
                        or (exclude and field_name in exclude)
                    ):
                        continue

                    _seen.add(field_name)

                    python_type = None
                    pydantic_field = None
                    if field_name in annotations and field_name in namespace:
                        python_type = annotations.pop(field_name)
                        pydantic_field = namespace[field_name]
                        if (
                            hasattr(pydantic_field, "default_factory")
                            and pydantic_field.default_factory
                        ):
                            pydantic_field = pydantic_field.default_factory()

                    elif field_name in annotations:
                        python_type = annotations.pop(field_name)
                        pydantic_field = (
                            None if Optional[python_type] == python_type else Ellipsis
                        )

                    else:
                        python_type, pydantic_field = ModelSchemaField(field, name)

                    field_values[field_name] = (python_type, pydantic_field)

                cls.__doc__ = namespace.get("__doc__", config["model"].__doc__)
                cls.__alias_map__ = {
                    getattr(model_field[1], "alias", None) or field_name: field_name
                    for field_name, model_field in field_values.items()
                }
                model_schema = create_model(
                    name,
                    __base__=cls,
                    __module__=cls.__module__,
                    __doc__=cls.__doc__,
                    **field_values,
                )

                return model_schema

        return cls


def _is_optional_field(annotation) -> bool:
    args = get_args(annotation)
    return (
        (get_origin(annotation) is Union or get_origin(annotation) is UnionType)
        and type(None) in args
        and len(args) == 2
        and any(inspect.isclass(arg) and issubclass(arg, ModelSchema) for arg in args)
    )


class ProxyGetterNestedObj:
    def __init__(self, obj: Any, schema_class):
        self._obj = obj
        self.schema_class = schema_class

    def get(self, key: Any, default: Any = None) -> Any:
        if "__" in key:
            # Allow double underscores aliases: first_name: str = Field(alias="user__first_name")
            keys_map = key.split("__")
            attr = reduce(lambda a, b: getattr(a, b, default), keys_map, self._obj)
        else:
            attr = getattr(self._obj, key, None)
        is_manager = issubclass(attr.__class__, Manager)

        alias = self.schema_class.__alias_map__[key]
        field = self.schema_class.model_fields[alias]

        typing_args = get_args(field.annotation)
        typing_origin = get_origin(field.annotation)
        if typing_origin == Union:
            outer_type_ = typing_args[0]
        elif typing_origin is None:
            outer_type_ = field.annotation
        # TODO do we have test for a list thingie?
        elif typing_args[0] == List:
            outer_type_ = typing_origin
        elif is_manager and field.annotation == List[Dict[str, int]]:
            outer_type_ = field.annotation
        else:
            outer_type_ = typing_args[0]

        if is_manager and outer_type_ == List[Dict[str, int]]:
            attr = list(attr.all().values("id"))
        elif is_manager:
            attr = list(attr.all())
        elif outer_type_ == int and issubclass(type(attr), Model):
            attr = attr.id
        elif inspect.isclass(type(attr)) and issubclass(type(attr), Enum):
            attr = attr.value
        elif issubclass(attr.__class__, ImageFieldFile) and issubclass(
            outer_type_, str
        ):
            attr = attr.name
        return attr

    def _get_annotation_objects(self, value, annotation):
        """Value is an object, and the value needs to resolve into a dict"""
        if isinstance(value, list):
            return [ProxyGetterNestedObj(o, annotation).dict() for o in value]
        return ProxyGetterNestedObj(value, annotation).dict()

    def dict(self) -> dict:
        """
        Might not be needed with "from_attributes=True" in model_config
        """
        fields = self.schema_class.model_fields
        data = {}
        for key, fieldinfo in fields.items():
            annotation = fieldinfo.annotation
            if get_origin(annotation) == list:
                # Pick the underlying annotation
                annotation = get_args(annotation)[0]

            if _is_optional_field(annotation):
                value = self.get(key)
                if value is None:
                    data[key] = None
                else:
                    non_none_type_annotation = next(
                        arg for arg in get_args(annotation) if arg is not type(None)
                    )
                    data[key] = self._get_annotation_objects(
                        value, non_none_type_annotation
                    )

            elif inspect.isclass(annotation) and issubclass(annotation, ModelSchema):
                data[key] = self._get_annotation_objects(self.get(key), annotation)
            else:
                key = fieldinfo.alias if fieldinfo.alias else key
                data[key] = self.get(key)
        return data


class ModelSchema(BaseModel, Generic[_M], metaclass=ModelSchemaMetaclass):
    def __eq__(self, other: Any) -> bool:
        result = super().__eq__(other)
        if isinstance(result, bool):
            return result

        if result is NotImplemented and isinstance(other, dict):
            return self.model_dump() == other
        return result

    def save(
        self,
        instance: Optional[_M] = None,
        partial: Optional[bool] = None,
        *args: Any,
        **kwargs: Any,
    ) -> _M:
        """Save the model instance to the database.

        This method saves the current model data to the database. If an instance is
        provided, it updates the existing instance with the data from the current object.
        If no instance is provided, it creates a new instance in the database.

        Args:
            instance: An optional model instance to update. If provided, the instance will be
                updated with the current model data. If None, a new instance will be created.
            partial: If True, only fields that have been explicitly set will be updated.
                If None or False, all fields will be updated/saved.
            *args: Additional positional arguments to pass to the model's save method.
            **kwargs: Additional keyword arguments to pass to the model's save method.

        Returns:
            The saved model instance.

        Raises:
            ValueError: If a field in the model data does not exist on the provided instance.
        """
        _ModelClass: _M = self.model_config["model"]
        data = self.model_dump() if not partial else self.model_dump(exclude_unset=True)
        if instance:
            # Update the existing instance with the new data
            for key, value in data.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
                else:
                    raise ValueError(f"Field {key} does not exist on the model.")
            instance.save(*args, **kwargs)
            return instance

        return _ModelClass.objects.create(**self.model_dump())

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        result = super().model_json_schema(*args, **kwargs)
        if cls.model_config.get("include"):
            include = cls.model_config.get("include", [])
            for key in list(result["properties"].keys()):
                if key not in include:
                    del result["properties"][key]

        if cls.model_config.get("exclude"):
            exclude = cls.model_config.get("exclude")
            for key in list(result["properties"].keys()):
                if key in exclude:
                    del result["properties"][key]

        return result

    @classmethod
    @no_type_check
    def get_field_names(cls) -> List[str]:
        if cls.model_config.get("exclude"):
            django_model_fields = cls.model_config["model"]._meta.get_fields()
            all_fields = [f.name for f in django_model_fields]
            return [
                name for name in all_fields if name not in cls.model_config["exclude"]
            ]
        return cls.model_config.get("include", [])

    @classmethod
    def from_orm(cls, *args, **kwargs):
        """Considered deprecated, use from django instead"""
        return cls.from_django(*args, **kwargs)

    @classmethod
    def from_django(cls, objs, many=False, context={}):
        if many:
            result_objs = []
            for obj in objs:
                obj = ProxyGetterNestedObj(obj, cls)
                instance = cls(**obj.dict())
                result_objs.append(cls.model_validate(instance, context=context))
            return result_objs

        obj = ProxyGetterNestedObj(objs, cls)
        instance = cls(**obj.dict())
        return cls.model_validate(instance, context=context)


_is_base_model_class_defined = True
