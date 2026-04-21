"""Canonical runtime repository facade and bundle reader."""

from trade_flow.legacy_site.services.precomputed_repository import get_repository

from .bundle_loader import RuntimeBundleDescriptor, load_bundle_descriptor

__all__ = ["RuntimeBundleDescriptor", "get_repository", "load_bundle_descriptor"]

