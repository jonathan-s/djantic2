from typing import Any, Optional, TypeVar, Union

from django.db.models import Model as DjangoModel

_M = TypeVar("_M", bound=DjangoModel)


class ModelSchemaMixin:
    def create(self, *args: Any, **kwargs: Any) -> _M:
        ModelDjangoClass: type[_M] = self.model_config["model"]

        record: _M = ModelDjangoClass._default_manager.create(**self.model_dump())

        return record

    def update(
        self, instance: _M, partial: Optional[bool] = None, *args: Any, **kwargs: Any
    ) -> _M:
        if not isinstance(instance, self.model_config["model"]):
            raise TypeError(
                "instance is not of the type {0}".format(self.model_config["model"])  # noqa
            )

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

    def save(
        self,
        instance: Optional[_M] = None,
        partial: Union[bool, None] = None,
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
                If Unset, all fields will be updated/saved.
            *args: Additional positional arguments to pass to the model's save method.
            **kwargs: Additional keyword arguments to pass to the model's save method.

        Returns:
            The saved model instance.

        Raises:
            ValueError: If a field in the model data does not exist on the provided instance.
        """

        if instance:
            record = self.update(instance, partial, *args, *kwargs)
            assert record is not None, "`update()` did not return an object instance."
        else:
            record = self.create(*args, **kwargs)
            assert record is not None, "`create()` did not return an object instance."
        return record
