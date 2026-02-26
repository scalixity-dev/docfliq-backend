"""SCORM manifest (imsmanifest.xml) parser.

Extracts organization structure (modules) and resources (lessons)
from a SCORM 1.2 / 2004 package.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass
class ScormResource:
    identifier: str
    href: str
    scorm_type: str  # "webcontent" or "sco"


@dataclass
class ScormItem:
    """A single item (lesson) within the organization tree."""

    identifier: str
    title: str
    resource_href: str | None = None
    children: list[ScormItem] = field(default_factory=list)


@dataclass
class ScormOrganization:
    """Top-level organization (module) from the manifest."""

    identifier: str
    title: str
    items: list[ScormItem] = field(default_factory=list)


@dataclass
class ScormManifest:
    """Parsed SCORM manifest."""

    schema_version: str | None = None
    default_org: str | None = None
    organizations: list[ScormOrganization] = field(default_factory=list)
    resources: dict[str, ScormResource] = field(default_factory=dict)
    entry_point: str | None = None


# IMS namespaces vary between SCORM versions
_NS_CANDIDATES = [
    "http://www.imsproject.org/xsd/imscp_rootv1p1p2",
    "http://www.imsglobal.org/xsd/imscp_v1p1",
    "",
]

_ADLCP_NS = "http://www.adlnet.org/xsd/adlcp_rootv1p2"


def _find(element: ET.Element, tag: str, ns: str) -> ET.Element | None:
    if ns:
        return element.find(f"{{{ns}}}{tag}")
    return element.find(tag)


def _findall(element: ET.Element, tag: str, ns: str) -> list[ET.Element]:
    if ns:
        return element.findall(f"{{{ns}}}{tag}")
    return element.findall(tag)


def _detect_namespace(root: ET.Element) -> str:
    root_tag = root.tag
    if root_tag.startswith("{"):
        ns = root_tag.split("}")[0].lstrip("{")
        return ns
    return ""


def parse_manifest(xml_content: str) -> ScormManifest:
    """Parse imsmanifest.xml content and return structured data."""
    root = ET.fromstring(xml_content)
    ns = _detect_namespace(root)

    manifest = ScormManifest()

    # Schema version
    metadata = _find(root, "metadata", ns)
    if metadata is not None:
        schema_ver = _find(metadata, "schemaversion", ns)
        if schema_ver is not None and schema_ver.text:
            manifest.schema_version = schema_ver.text.strip()

    # Resources
    resources_el = _find(root, "resources", ns)
    if resources_el is not None:
        for res in _findall(resources_el, "resource", ns):
            identifier = res.get("identifier", "")
            href = res.get("href", "")
            scorm_type = res.get(f"{{{_ADLCP_NS}}}scormtype", "")
            if not scorm_type:
                scorm_type = res.get("scormtype", res.get("type", "webcontent"))
            manifest.resources[identifier] = ScormResource(
                identifier=identifier,
                href=href,
                scorm_type=scorm_type,
            )

    # Organizations
    orgs_el = _find(root, "organizations", ns)
    if orgs_el is not None:
        manifest.default_org = orgs_el.get("default", "")

        for org_el in _findall(orgs_el, "organization", ns):
            org = _parse_organization(org_el, ns, manifest.resources)
            manifest.organizations.append(org)

    # Determine entry point
    if manifest.resources:
        # Prefer the first SCO resource
        for res in manifest.resources.values():
            if res.scorm_type.lower() == "sco" and res.href:
                manifest.entry_point = res.href
                break
        if manifest.entry_point is None:
            first = next(iter(manifest.resources.values()))
            if first.href:
                manifest.entry_point = first.href

    return manifest


def _parse_organization(
    org_el: ET.Element, ns: str, resources: dict[str, ScormResource],
) -> ScormOrganization:
    identifier = org_el.get("identifier", "")
    title_el = _find(org_el, "title", ns)
    title = title_el.text.strip() if title_el is not None and title_el.text else identifier

    items = []
    for item_el in _findall(org_el, "item", ns):
        items.append(_parse_item(item_el, ns, resources))

    return ScormOrganization(identifier=identifier, title=title, items=items)


def _parse_item(
    item_el: ET.Element, ns: str, resources: dict[str, ScormResource],
) -> ScormItem:
    identifier = item_el.get("identifier", "")
    identifierref = item_el.get("identifierref", "")

    title_el = _find(item_el, "title", ns)
    title = title_el.text.strip() if title_el is not None and title_el.text else identifier

    resource_href = None
    if identifierref and identifierref in resources:
        resource_href = resources[identifierref].href

    children = []
    for child_el in _findall(item_el, "item", ns):
        children.append(_parse_item(child_el, ns, resources))

    return ScormItem(
        identifier=identifier,
        title=title,
        resource_href=resource_href,
        children=children,
    )
