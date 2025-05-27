from typing import Optional, TypeVar

import pytest
from django.db import models
from pydantic import Field

from djantic import ModelSchema
from testapp.models import Profile, User


@pytest.mark.django_db
def test_save_new_instance():
    """
    Test creating a new model instance using the save() method.
    """

    class UserSchema(ModelSchema[User]):
        class Config:
            model = User
            include = ("first_name", "last_name", "email")

    # Create a user schema instance
    user_schema = UserSchema(
        first_name="John", last_name="Doe", email="john.doe@example.com"
    )

    # Save it to the database
    user_instance = user_schema.save()

    # Verify it was saved correctly
    assert user_instance.id is not None
    assert user_instance.first_name == "John"
    assert user_instance.last_name == "Doe"
    assert user_instance.email == "john.doe@example.com"

    # Verify it's in the database
    user_from_db = User.objects.get(id=user_instance.id)
    assert user_from_db.first_name == "John"
    assert user_from_db.last_name == "Doe"
    assert user_from_db.email == "john.doe@example.com"


@pytest.mark.django_db
def test_update_existing_instance():
    """
    Test updating an existing model instance using the save() method.
    """
    # Create a user directly in the database
    user = User.objects.create(
        first_name="Jane", last_name="Smith", email="jane.smith@example.com"
    )

    class UserSchema(ModelSchema[User]):
        class Config:
            model = User
            include = ["first_name", "last_name", "email"]

    # Create a schema with updated data
    user_schema = UserSchema.model_validate(
        {
            "first_name": "Janet",
            "last_name": "Smith-Johnson",
            "email": "janet2.smith@example.com",
        },
    )

    # Update the existing user
    updated_user = user_schema.save(instance=user)

    # Verify it was the same instance but updated
    assert updated_user.id == user.id
    assert updated_user.first_name == "Janet"
    assert updated_user.last_name == "Smith-Johnson"
    assert updated_user.email == "janet2.smith@example.com"

    # Verify it's updated in the database
    user_from_db = User.objects.get(id=user.id)
    assert user_from_db.first_name == "Janet"
    assert user_from_db.last_name == "Smith-Johnson"
    assert user_from_db.email == "janet2.smith@example.com"


@pytest.mark.django_db
def test_partial_update():
    class UserPartialSchema(ModelSchema[User]):
        first_name: Optional[str]
        last_name: Optional[str]
        email: Optional[str]

        class Config:
            exclude = ("created_at", "updated_at")

    user = User.objects.create(
        first_name="John", last_name="Doe", email="john.doe@example.com"
    )

    # Create a schema with only some fields set
    user_schema = UserPartialSchema(email="email@email.com", first_name="John")

    # Update only the set fields
    updated_user = user_schema.save(instance=user, partial=True)

    # Verify only first_name was updated
    assert updated_user.id == user.id
    assert updated_user.first_name == "John"
    assert updated_user.last_name == "Doe"
    assert updated_user.email == "email@email.com"


@pytest.mark.django_db
def test_generic_type_inference_no_model_param():
    """
    Test generic type inference without explicitly defining the model in Config.
    """

    class UserSchema(ModelSchema[User]):
        class Config:
            include = ("first_name", "last_name", "email")

    # Create a user schema instance
    user_schema = UserSchema(
        first_name="Robert", last_name="Brown", email="robert.brown@example.com"
    )

    # Save it to the database
    user_instance = user_schema.save()

    # Verify it was saved correctly
    assert user_instance.id is not None
    assert user_instance.first_name == "Robert"
    assert user_instance.last_name == "Brown"
    assert user_instance.email == "robert.brown@example.com"

    # Verify the model was correctly inferred from the generic type
    assert user_schema.model_config["model"] == User
