"""Contract tests for the merged DAV package (manifest, provider, tool set)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Contracts of the released shaba/caldav 0.0.1 and shaba/carddav 0.0.1 plugins.
EXPECTED_TOOLS = {
    "create_event": ["calendar", "summary", "start", "end", "description", "location"],
    "create_task": ["calendar", "summary", "due", "description"],
    "list_calendars": [],
    "list_events": ["calendar", "start", "end"],
    "list_tasks": ["calendar", "only_incomplete"],
    "search_events": ["calendar", "query", "start", "end"],
    "create_contact": ["full_name", "emails", "phones", "org", "title", "addressbook"],
    "get_contact": ["identifier", "addressbook"],
    "list_addressbooks": [],
    "list_contacts": ["addressbook"],
    "search_contacts": ["query", "addressbook"],
}

CREDENTIAL_FIELDS = [
    "caldav_url", "caldav_username", "caldav_password",
    "carddav_url", "carddav_username", "carddav_password",
]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def provider():
    return load_yaml(ROOT / "provider/dav.yaml")


def tool_docs():
    docs = {}
    for rel in provider()["tools"]:
        doc = load_yaml(ROOT / rel)
        docs[doc["identity"]["name"]] = doc
    return docs


def test_manifest_shape():
    manifest = load_yaml(ROOT / "manifest.yaml")
    assert manifest["author"] == "shaba"
    assert manifest["name"] == "dav"
    assert manifest["plugins"]["tools"] == ["provider/dav.yaml"]
    assert not manifest["plugins"].get("datasources")
    assert manifest["meta"]["runner"]["language"] == "python"
    assert manifest["meta"]["runner"]["version"] == "3.12"


def test_provider_identity_and_tools_count():
    prov = provider()
    assert prov["identity"]["name"] == "dav"
    assert prov["identity"]["author"] == "shaba"
    assert len(prov["tools"]) == 11
    assert all(
        rel.startswith(("tools/caldav/", "tools/carddav/"))
        for rel in prov["tools"])


def test_tool_names_and_parameters_match_released_contracts():
    docs = tool_docs()
    assert set(docs) == set(EXPECTED_TOOLS)
    for name, expected_params in EXPECTED_TOOLS.items():
        params = [p["name"] for p in (docs[name].get("parameters") or [])]
        assert params == expected_params, name


def test_all_python_sources_exist():
    paths = [provider()["extra"]["python"]["source"]]
    for rel in provider()["tools"]:
        paths.append(load_yaml(ROOT / rel)["extra"]["python"]["source"])
    for src in paths:
        assert (ROOT / src.split(":")[0]).is_file(), src


def test_credential_fields_prefixed_and_optional():
    creds = provider()["credentials_for_provider"]
    assert set(creds) == set(CREDENTIAL_FIELDS)
    for field in CREDENTIAL_FIELDS:
        assert creds[field]["required"] is False, field
