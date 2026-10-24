from __future__ import annotations

import json

from pdf_to_surveyjs_agent.tools import validate_survey, validate_survey_json


def test_accepts_top_level_elements() -> None:
    survey = {
        "title": "Registration",
        "elements": [
            {"type": "text", "name": "full_name", "title": "Full name", "isRequired": True},
            {
                "type": "radiogroup",
                "name": "attendance",
                "title": "Will you attend?",
                "choices": ["Yes", "No"],
            },
        ],
    }

    result = validate_survey(survey)

    assert result.valid is True
    assert result.errors == []


def test_accepts_pages_and_choice_objects() -> None:
    survey = {
        "pages": [
            {
                "name": "page1",
                "elements": [
                    {
                        "type": "dropdown",
                        "name": "department",
                        "title": "Department",
                        "choices": [
                            {"value": "eng", "text": "Engineering"},
                            {"value": "ops", "text": "Operations"},
                        ],
                    }
                ],
            }
        ]
    }

    assert validate_survey(survey).valid is True


def test_rejects_invalid_json() -> None:
    result = validate_survey_json('{"elements": [}')

    assert result["valid"] is False
    assert "Invalid JSON" in result["errors"][0]


def test_rejects_missing_structure() -> None:
    result = validate_survey({"title": "Empty"})

    assert result.valid is False
    assert "elements" in result.errors[0]


def test_rejects_unsupported_type_and_duplicate_names() -> None:
    survey = {
        "elements": [
            {"type": "text", "name": "email", "title": "Email"},
            {"type": "text", "name": "email", "title": "Confirm email"},
            {"type": "madeup", "name": "other", "title": "Other"},
        ]
    }

    result = validate_survey(survey)

    assert result.valid is False
    assert any("Duplicate" in error for error in result.errors)
    assert any("not supported" in error for error in result.errors)


def test_choice_question_requires_choices() -> None:
    result = validate_survey(
        {"elements": [{"type": "radiogroup", "name": "answer", "title": "Answer"}]}
    )

    assert result.valid is False
    assert any("choices" in error for error in result.errors)


def test_required_and_visibility_types_are_checked() -> None:
    result = validate_survey(
        {
            "elements": [
                {
                    "type": "text",
                    "name": "details",
                    "title": "Details",
                    "isRequired": "yes",
                    "visibleIf": True,
                }
            ]
        }
    )

    assert result.valid is False
    assert len(result.errors) == 2


def test_json_validator_accepts_serialized_survey() -> None:
    payload = json.dumps(
        {"elements": [{"type": "boolean", "name": "consent", "title": "I agree"}]}
    )

    result = validate_survey_json(payload)

    assert result == {"valid": True, "errors": [], "warnings": []}

