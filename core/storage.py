"""
Custom storage classes for StudyGrade.
Provides lenient static files manifest handling to prevent 500 errors on missing hashes.
"""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SafeWhiteNoiseStorage(CompressedManifestStaticFilesStorage):
    """
    WhiteNoise storage that does not crash if an unhashed asset is referenced.
    Falls back gracefully to the original file path.
    """
    manifest_strict = False
