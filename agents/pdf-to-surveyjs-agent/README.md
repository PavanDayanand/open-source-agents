# PDF-to-SurveyJS Agent

> Convert a text-based PDF form into a validated, human-reviewable SurveyJS JSON draft with Google ADK and Gemma.

---

## Overview

### Problem Statement & Intended Users

- **Problem**: Recreating existing PDF forms online is slow and error-prone.
- **Intended users**: Developers and operations teams preparing a first SurveyJS draft from an existing form.

### Key Features

- Extracts text deterministically with PyMuPDF; scanned PDFs receive an explicit OCR warning.
- Uses a configurable Gemma model through Google ADK to infer conservative form fields.
- Constrains the final model response with an ADK structured-output schema and safely handles JSON surrounded by explanatory text.
- Validates JSON syntax, structure, supported question types, names, choices, and common property types.
- Makes at most one model repair attempt by default, then reports remaining validation errors.
- Includes extraction-only and validation-only modes that do not call a model.

The result is a draft. A human must review it before use. This project does not publish forms or collect submissions.

---

## Technical Stack

- **Language**: Python 3.10+
- **Agent framework**: Google Agent Development Kit (ADK) 2.12
- **Model**: Gemma 4 26B MoE IT by default (`gemma-4-26b-a4b-it`), configurable
- **PDF extraction**: PyMuPDF
- **Tests**: pytest

The default model identifier reflects the Gemma model documented for the Gemini API when this project was built. Availability can vary by account and region, so the model is isolated in `PDF_SURVEY_MODEL`.

---

## Architecture & Data Flow

```text
[User-selected PDF]
        |
        v
[PyMuPDF extraction] -- no useful text --> [Clear OCR/not-supported error]
        |
        v
[Untrusted text boundary] --> [ADK agent + configured Gemma model]
                                      |
                                      v
                           [Deterministic validator]
                              |              |
                            valid         invalid
                              |              |
                    [JSON + warnings]  [Bounded repair]
```

PDF content is treated as data, not instructions. The CLI performs deterministic extraction before invoking the model and validates every model response locally.

---

## Prerequisites

- Python 3.10 or newer
- A Google AI Studio API key with access to the configured Gemma model
- Internet access for the model request

OCR, local GPU setup, public hosting, and form-submission storage are not required or included.

---

## Installation & Setup

```bash
cd agents/pdf-to-surveyjs-agent
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Put your own API key in `.env`. The file is ignored by Git.

---

## Configuration & Environment Variables

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `GOOGLE_API_KEY` | Yes for conversion | None | Google AI Studio API key. `GEMINI_API_KEY` is also recognized. |
| `PDF_SURVEY_MODEL` | No | `gemma-4-26b-a4b-it` | Gemma model identifier passed to ADK. |
| `PDF_SURVEY_MAX_RETRIES` | No | `1` | Repair attempts after the first response; allowed range is 0-2. |
| `PDF_SURVEY_ALLOWED_ROOT` | No | Current directory | Directory the ADK-exposed extraction tool may read. Explicit CLI paths are not restricted. |

No credential is required for `--extract-only`, `--validate-json`, or tests. If credentials are missing, conversion exits with a clear configuration error and does not substitute another model.

---

## How to Run

Create the synthetic sample PDF:

```bash
python examples/create_sample_pdf.py
```

Inspect extraction without sending text to a model:

```bash
python main.py examples/sample_form.generated.pdf --extract-only
```

Convert a PDF and save the reviewable draft:

```bash
python main.py examples/sample_form.generated.pdf --output output/sample_output.json
```

Validate an existing SurveyJS object without a model call:

```bash
python main.py --validate-json examples/sample_survey.json
```

`examples/sample_survey.json` is a documented example, not a claim that a live Gemma request was made in this checkout.

### Optional ADK Developer UI

The package exports the conventional `root_agent` definition. From the project directory, use ADK's local UI for interactive inspection:

```bash
adk web .
```

The purpose-built `main.py` workflow is recommended for conversion because it owns deterministic extraction, validation, and bounded repair.

---

## Example Input & Output

The generated sample PDF contains these synthetic fields:

```text
Full name (required)
Email address (required)
Experience level: Beginner / Intermediate / Advanced
May we email you workshop updates? Yes / No
```

A successful conversion returns an envelope like this:

```json
{
  "survey": {
    "title": "Community Workshop Registration",
    "elements": [
      {
        "type": "text",
        "name": "full_name",
        "title": "Full name",
        "isRequired": true
      }
    ]
  },
  "warnings": ["Review field names and required flags before publishing."],
  "model": "gemma-4-26b-a4b-it",
  "attempts": 1
}
```

The complete SurveyJS object is in `examples/sample_survey.json`, ready for the validation-only command or a SurveyJS application.

---

## How to Test

```bash
pytest -q
```

The suite creates temporary synthetic PDFs and covers extraction, low-text handling, invalid files, path restrictions, valid page/element layouts, malformed JSON, unsupported types, duplicate names, choice requirements, and missing model credentials. It does not spend model tokens.

---

## Validation Scope

This MVP accepts top-level `elements` or `pages[].elements` and a conservative set of common SurveyJS types. Checks include:

- a JSON object with at least one question;
- supported question `type` values;
- non-empty, unique question `name` values;
- string titles when present, with a warning when missing;
- non-empty `choices` for choice questions;
- boolean `isRequired` and string `visibleIf` values.

These checks verify useful structure, not the entire SurveyJS runtime schema or semantic correctness.

---

## Known Limitations

- No OCR; image-only/scanned PDFs are reported rather than guessed.
- Complex visual layout, tables, signatures, and handwriting may be lost during extraction.
- The model can omit or misclassify fields. Validation checks shape, not meaning.
- Very large PDFs can exceed hosted-model token quotas; automatic page chunking is not yet included.
- Conditional logic is included only when the model finds explicit evidence; a reviewer must confirm it.
- Input is limited to 15 MB and 100 pages. Model-bound extracted text is capped at 100,000 characters.
- Gemma access and identifiers can change. Override `PDF_SURVEY_MODEL` when required.

---

## Security & Privacy Considerations

- PDF text is untrusted and explicitly delimited in the model prompt.
- The application never executes commands, code, or instructions found in a PDF.
- The ADK-exposed extraction tool cannot read outside `PDF_SURVEY_ALLOWED_ROOT`.
- During conversion, document text is sent to the configured Google model endpoint. Do not use sensitive documents unless that transmission is permitted.
- The application does not log PDF contents, persist submissions, or publish forms.
- `.env`, generated output, caches, and virtual environments are excluded from Git.
- Generated forms are not guaranteed legally or operationally correct; keep human review in the loop.

---

## Future Improvements

- [ ] Add opt-in OCR with confidence reporting and tests.
- [ ] Expand validation against a maintained SurveyJS schema.
- [ ] Add a separately documented local Gemma runtime.
- [ ] Add evaluation fixtures for representative public forms.

---

## License

This project is contributed under the repository's MIT license.
