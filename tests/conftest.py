"""Suite-wide test defaults."""
import os

# The siting engine's live overlays (U.S. Drought Monitor, FEMA NRI) are network
# calls. Default them OFF for the whole suite so tests are fast, deterministic,
# and offline. Tests that exercise the live path re-enable it per-test with
# monkeypatch.setenv and/or mock the fetch functions directly.
os.environ.setdefault("NEMO_SITING_LIVE", "0")
