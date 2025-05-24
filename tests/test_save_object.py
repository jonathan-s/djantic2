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
            exclude = ("id", "created_at", "updated_at")

    # Create a schema with updated data
    user_schema = UserSchema(
        first_name="Janet", last_name="Smith-Johnson", email="janet.smith@example.com"
    )

    # Update the existing user
    updated_user = user_schema.save(instance=user)

    # Verify it was the same instance but updated
    assert updated_user.id == user.id
    assert updated_user.first_name == "Janet"
    assert updated_user.last_name == "Smith-Johnson"
    assert updated_user.email == "janet.smith@example.com"

    # Verify it's updated in the database
    user_from_db = User.objects.get(id=user.id)
    assert user_from_db.first_name == "Janet"
    assert user_from_db.last_name == "Smith-Johnson"
    assert user_from_db.email == "janet.smith@example.com"


@pytest.mark.django_db
def test_partial_update():
    """
    Test partial updating of an existing model instance using the save() method.
    """
    # Create a user directly in the database
    user = User.objects.create(
        first_name="Alex", last_name="Johnson", email="alex.johnson@example.com"
    )

    class UserSchema(ModelSchema[User]):
        email: Optional[str]

        class Config:
            model = User
            include = ("first_name", "last_name", "email")

    # Create a schema with only some fields set
    user_schema = UserSchema(first_name="Alexander")

    # Update only the set fields
    updated_user = user_schema.save(instance=user, partial=True)

    # Verify only first_name was updated
    assert updated_user.id == user.id
    assert updated_user.first_name == "Alexander"
    assert updated_user.last_name == "Johnson"  # Unchanged
    assert updated_user.email == "alex.johnson@example.com"  # Unchanged


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


@pytest.mark.django_db
def test_related_model_save():
    """
    Test saving a model with a related model field.
    """

    class ProfileSchema(ModelSchema[Profile]):
        class Config:
            model = Profile

    class UserSchema(ModelSchema[User]):
        profile: Optional[ProfileSchema] = None

        class Config:
            model = User
            include = ("first_name", "last_name", "email")

    # Create a user schema instance
    user_schema = UserSchema(
        first_name="Michael", last_name="Wilson", email="michael.wilson@example.com"
    )

    # Save the user first
    user_instance = user_schema.save()

    # Create and save a profile
    profile_schema = ProfileSchema(
        website="https://example.com", location="New York", user=user_instance.id
    )

    # We need to manually set the user for the profile
    profile = profile_schema.save()

    # Retrieve the user with the profile
    user_with_profile = User.objects.get(id=user_instance.id)
    assert hasattr(user_with_profile, "profile")
    assert user_with_profile.profile.website == "https://example.com"
    assert user_with_profile.profile.location == "New York"
