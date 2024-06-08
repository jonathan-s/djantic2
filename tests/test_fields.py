import pytest
from pydantic import ConfigDict
from testapp.models import Configuration, Listing, Preference, Record, Searchable, User

from pydantic import (
    ValidationInfo,
    field_validator,
    ValidationError,
)

from djantic import ModelSchema


@pytest.mark.django_db
def test_schema_without_include_and_exclude():
    """
    Using a schema without include and exclude populates userschema correctly
    Optional foreign key handled gracefully.
    """

    user = User.objects.create(
        first_name="Jordan", last_name="Eremieff", email="jordan@eremieff.com"
    )

    class UserSchema(ModelSchema):
        model_config = ConfigDict(model=User)

    dumped = UserSchema.from_django(user).model_dump()
    # These values are here, but a hassle to use freeze gun.
    dumped.pop("updated_at")
    dumped.pop("created_at")

    assert dumped == {
        "first_name": "Jordan",
        "id": 1,
        "email": "jordan@eremieff.com",
        "profile": None,
        "last_name": "Eremieff",
    }


@pytest.mark.django_db
def test_context_for_field():

    def get_context():
        return {'check_title': lambda x: x.istitle()}

    class UserSchema(ModelSchema):
        model_config = ConfigDict(
            model=User,
            revalidate_instances='always'
        )

        @field_validator('first_name', mode="before", check_fields=False)
        @classmethod
        def validate_first_name(cls, v: str, info: ValidationInfo):
            if not info.context:
                return v

            check_title = info.context.get('check_title')
            if check_title and not check_title(v):
                raise ValueError('First name needs to be a title')
            return v

    user = User.objects.create(first_name="hello", email="a@a.com")
    with pytest.raises(ValidationError):
        UserSchema.from_django(user, context=get_context())


@pytest.mark.django_db
def test_unhandled_field_type():
    class SearchableSchema(ModelSchema):
        model_config = ConfigDict(model=Searchable)

    assert SearchableSchema.model_json_schema() == {
        "description": "Searchable(id, title, search_vector)",
        "properties": {
            "id": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
                "description": "id",
                "title": "Id",
            },
            "title": {
                "description": "title",
                "maxLength": 255,
                "title": "Title",
                "type": "string",
            },
            "search_vector": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
                "description": "search_vector",
                "title": "Search Vector",
            },
        },
        "required": ["title"],
        "title": "SearchableSchema",
        "type": "object",
    }
    searchable = Searchable.objects.create(title="My content")
    assert SearchableSchema.from_django(searchable).model_dump() == {
        "id": 1,
        "title": "My content",
        "search_vector": None,
    }


@pytest.mark.django_db
def test_custom_field():
    """
    Test a model using custom field subclasses.
    """

    class RecordSchema(ModelSchema):
        model_config = ConfigDict(model=Record, include=["id", "title", "items"])

    assert RecordSchema.model_json_schema() == {
        "description": "A generic record model.",
        "properties": {
            "id": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
                "description": "id",
                "title": "Id",
            },
            "title": {
                "description": "title",
                "maxLength": 20,
                "title": "Title",
                "type": "string",
            },
            "items": {
                "anyOf": [
                    {
                        "contentMediaType": "application/json",
                        "contentSchema": {},
                        "type": "string",
                    },
                    {"type": "object"},
                    {"items": {}, "type": "array"},
                ],
                "description": "items",
                "title": "Items",
            },
        },
        "required": ["title"],
        "title": "RecordSchema",
        "type": "object",
    }


@pytest.mark.django_db
def test_postgres_json_field():
    """
    Test generating a model_json_schema for multiple Postgres JSON fields.
    """

    class ConfigurationSchema(ModelSchema):
        model_config = ConfigDict(
            model=Configuration, include=["permissions", "changelog", "metadata"]
        )

    assert ConfigurationSchema.model_json_schema() == {
        "description": "A configuration container.",
        "properties": {
            "permissions": {
                "anyOf": [
                    {
                        "contentMediaType": "application/json",
                        "contentSchema": {},
                        "type": "string",
                    },
                    {"type": "object"},
                    {"items": {}, "type": "array"},
                ],
                "description": "permissions",
                "title": "Permissions",
            },
            "changelog": {
                "anyOf": [
                    {
                        "contentMediaType": "application/json",
                        "contentSchema": {},
                        "type": "string",
                    },
                    {"type": "object"},
                    {"items": {}, "type": "array"},
                ],
                "description": "changelog",
                "title": "Changelog",
            },
            "metadata": {
                "anyOf": [
                    {
                        "contentMediaType": "application/json",
                        "contentSchema": {},
                        "type": "string",
                    },
                    {"type": "object"},
                    {"items": {}, "type": "array"},
                    {"type": "null"},
                ],
                "default": None,
                "description": "metadata",
                "title": "Metadata",
            },
        },
        "title": "ConfigurationSchema",
        "type": "object",
    }


@pytest.mark.django_db
def test_lazy_choice_field():
    """
    Test generating a dynamic enum choice field.
    """

    class RecordSchema(ModelSchema):
        model_config = ConfigDict(
            model=Record, include=["record_type", "record_status"]
        )

    assert RecordSchema.model_json_schema() == {
        "$defs": {
            "RecordSchemaRecordStatusEnum": {
                "enum": [0, 1, 2],
                "title": "RecordSchemaRecordStatusEnum",
                "type": "integer",
            },
            "RecordSchemaRecordTypeEnum": {
                "enum": ["NEW", "OLD"],
                "title": "RecordSchemaRecordTypeEnum",
                "type": "string",
            },
        },
        "description": "A generic record model.",
        "properties": {
            "record_type": {
                "allOf": [{"$ref": "#/$defs/RecordSchemaRecordTypeEnum"}],
                "default": "NEW",
                "description": "record_type",
                "title": "Record Type",
            },
            "record_status": {
                "allOf": [{"$ref": "#/$defs/RecordSchemaRecordStatusEnum"}],
                "default": 0,
                "description": "record_status",
                "title": "Record Status",
            },
        },
        "title": "RecordSchema",
        "type": "object",
    }


@pytest.mark.django_db
def test_enum_choices():
    class PreferenceSchema(ModelSchema):
        model_config = ConfigDict(model=Preference, use_enum_values=True)

    assert PreferenceSchema.model_json_schema() == {
        "$defs": {
            "PreferenceSchemaPreferredFoodEnum": {
                "enum": ["ba", "ap"],
                "title": "PreferenceSchemaPreferredFoodEnum",
                "type": "string",
            },
            "PreferenceSchemaPreferredGroupEnum": {
                "enum": [1, 2],
                "title": "PreferenceSchemaPreferredGroupEnum",
                "type": "integer",
            },
            "PreferenceSchemaPreferredMusicianEnum": {
                "enum": ["tom_jobim", "sinatra", ""],
                "title": "PreferenceSchemaPreferredMusicianEnum",
                "type": "string",
            },
            "PreferenceSchemaPreferredSportEnum": {
                "enum": ["football", "basketball", ""],
                "title": "PreferenceSchemaPreferredSportEnum",
                "type": "string",
            },
        },
        "description": "Preference(id, name, preferred_food, preferred_group, preferred_sport, preferred_musician)",
        "properties": {
            "id": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
                "description": "id",
                "title": "Id",
            },
            "name": {
                "description": "name",
                "maxLength": 128,
                "title": "Name",
                "type": "string",
            },
            "preferred_food": {
                "allOf": [{"$ref": "#/$defs/PreferenceSchemaPreferredFoodEnum"}],
                "default": "ba",
                "description": "preferred_food",
                "title": "Preferred Food",
            },
            "preferred_group": {
                "allOf": [{"$ref": "#/$defs/PreferenceSchemaPreferredGroupEnum"}],
                "default": 1,
                "description": "preferred_group",
                "title": "Preferred Group",
            },
            "preferred_sport": {
                "anyOf": [
                    {"$ref": "#/$defs/PreferenceSchemaPreferredSportEnum"},
                    {"type": "null"},
                ],
                "default": None,
                "description": "preferred_sport",
                "title": "Preferred Sport",
            },
            "preferred_musician": {
                "anyOf": [
                    {"$ref": "#/$defs/PreferenceSchemaPreferredMusicianEnum"},
                    {"type": "null"},
                ],
                "default": "",
                "description": "preferred_musician",
                "title": "Preferred Musician",
            },
        },
        "required": ["name"],
        "title": "PreferenceSchema",
        "type": "object",
    }

    preference = Preference.objects.create(
        name="Jordan",
        preferred_sport="",
        preferred_musician=None,
    )
    assert PreferenceSchema.from_django(preference).model_dump() == {
        "id": 1,
        "name": "Jordan",
        # default choice dumped
        "preferred_food": "ba",
        # default choice dumped
        "preferred_group": 1,
        "preferred_sport": "",
        "preferred_musician": None,
    }


@pytest.mark.skip(reason="Enums seems unique, but need other approach to verify")
@pytest.mark.django_db
def test_enum_choices_generates_unique_enums():
    class PreferenceSchema(ModelSchema):
        model_config = ConfigDict(model=Preference, use_enum_values=True)

    class PreferenceSchema2(ModelSchema):
        model_config = ConfigDict(model=Preference, use_enum_values=True)

    assert str(PreferenceSchema2.model_fields["preferred_food"].type_) != str(
        PreferenceSchema.model_fields["preferred_food"].type_
    )


@pytest.mark.django_db
def test_listing():
    """
    Testing the following properties for a field.
    - nullable foreign key
    - array field
    """

    class ListingSchema(ModelSchema):
        model_config = ConfigDict(model=Listing, use_enum_values=True)

    assert ListingSchema.model_json_schema() == {
        "description": "Listing(id, items, content_type)",
        "properties": {
            "id": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
                "description": "id",
                "title": "Id",
            },
            "items": {
                "description": "items",
                "items": {"type": "string"},
                "title": "Items",
                "type": "array",
            },
            "content_type": {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "default": None,
                "description": "id",
                "title": "Content Type",
            },
        },
        "required": ["items"],
        "title": "ListingSchema",
        "type": "object",
    }

    preference = Listing(items=["a", "b"])
    assert ListingSchema.from_django(preference).dict() == {
        "content_type": None,
        "id": None,
        "items": ["a", "b"],
    }
