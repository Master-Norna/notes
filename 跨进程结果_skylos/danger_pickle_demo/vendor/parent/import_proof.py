"""Minimal stand-in for skylos' import_proof helper.

The demo only exercises the pickle protocol, never shadowing resolution, so
``provider_is_unshadowed`` answers False.  The real module lives at
skylos/rules/danger/import_proof.py in the upstream snapshot.
"""


def provider_is_unshadowed(name, filename, project_root):
    return False
