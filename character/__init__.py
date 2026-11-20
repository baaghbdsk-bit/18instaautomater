"""
character — single-character identity and variation engine.

A small, dependency-free module set that keeps ONE fictional adult AI
influencer visually consistent across static Instagram quote-image posts:

  * profile.py      — the canonical, immutable character profile
  * variations.py   — curated, coherent scene/outfit/pose combinations
  * consistency.py  — seed/reference config and identity-preservation checks

The fixed identity text stabilises *described attributes* only. It does NOT
guarantee the same face: see the caveat in profile.CharacterProfile.
"""
