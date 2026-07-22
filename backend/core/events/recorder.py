"""Legacy recorder — delegates to event bus."""
from core.events.bus import record_event

# Export the same function signature for backward compatibility
__all__ = ["record_event"]
