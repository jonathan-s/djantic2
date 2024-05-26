import pytest
from testapp.models import User
from django.core.exceptions import ValidationError

from pydantic import ConfigDict
from djantic import ModelSchema


@pytest.fixture
def user():
    user = User.objects.create(
        first_name="Jordan", last_name="Eremieff", email="jordan@eremieff.com"
    )
    return user


@pytest.mark.django_db
def test_to_django_validation_failure(user):
    """
    An incomplete schema throws a ValidationError
    """

    class UserSchema(ModelSchema):
        model_config = ConfigDict(model=User, include=["id", "first_name"])

    schema = UserSchema.from_django(user)

    with pytest.raises(ValidationError):
        UserSchema.to_django(schema.model_dump())

    with pytest.raises(ValidationError):
        UserSchema.to_django(schema)


@pytest.mark.django_db
def test_validate_false(user):
    """
    Optionally you can choose to not validate in to django,
    you may then need to add more fields for the object to be valid
    """

    class UserSchema(ModelSchema):
        model_config = ConfigDict(model=User, include=["id", "first_name"])

    schema = UserSchema.from_django(user)

    obj = UserSchema.to_django(schema, validate=False)

    assert obj.email != user.email, "No email in schema, so is not added in object"
    assert obj.id == user.id
    assert obj.first_name == user.first_name


@pytest.mark.django_db
def test_many_objects(user):
    """Test many objects"""
    class UserSchema(ModelSchema):
        model_config = ConfigDict(model=User)

    schema = UserSchema.from_django(user)
    obj_schema = UserSchema.to_django([schema, schema], many=True)

    assert len(obj_schema) == 2
    assert obj_schema[0].id == user.id
    assert obj_schema[1].id == user.id


@pytest.mark.django_db
def test_invalid_many_objs(user):
    """Validation works as expected using many objs"""
    class UserSchema(ModelSchema):
        model_config = ConfigDict(model=User, include=["id"])

    schema = UserSchema.from_django(user)
    with pytest.raises(ValidationError):
        UserSchema.to_django([schema], many=True)


@pytest.mark.django_db
def test_with_foreign_key_models():
    pass


@pytest.mark.django_db
def test_successful_transform(user):
    """A successful transform from dict/schema to django obj"""

    class UserSchema(ModelSchema):
        model_config = ConfigDict(model=User)

    schema = UserSchema.from_django(user)

    obj_dump = UserSchema.to_django(schema.model_dump())
    obj_schema = UserSchema.to_django(schema)

    assert user == obj_dump
    assert user == obj_schema
