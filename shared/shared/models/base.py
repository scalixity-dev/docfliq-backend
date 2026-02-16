from pydantic import ConfigDict

# Base config: strip whitespace, validate on assignment
model_config = ConfigDict(
    str_strip_whitespace=True,
    validate_assignment=True,
    extra="forbid",
)
