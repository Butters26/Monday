#!/usr/bin/env python3
"""Phase 4 compatibility name for the native clean Mercy Thalamus.

Phase 4 is folded into ``thalamus.Thalamus``. There is no wrapper, legacy base
class, monkey-patching, or inherited semantic-repair implementation underneath
this name anymore.
"""

from thalamus import Thalamus

Phase4Thalamus = Thalamus

__all__ = ["Phase4Thalamus", "Thalamus"]
