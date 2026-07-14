"""SiliconForge backends package."""

from siliconforge.backends.base import Simulator, CircuitState, TransientResult, BenchmarkMetrics
from siliconforge.backends.reference_ode import ReferenceOdeBackend

try:
    from siliconforge.backends.xyce import XyceBackend
except ImportError:  # pragma: no cover - Xyce optional
    XyceBackend = None

__all__ = [
    "Simulator",
    "CircuitState",
    "TransientResult",
    "BenchmarkMetrics",
    "ReferenceOdeBackend",
    "XyceBackend",
]

if __name__ == "__main__":
    try:
        from siliconforge.backends.reference_ode import ReferenceOdeBackend as _Ref
        from siliconforge.backends.xyce import XyceBackend as _Xyce

        for _backend in (_Ref(), _Xyce() if _Xyce is not None else None):
            if _backend is None:
                continue
            assert callable(_backend.load)
            assert callable(_backend.reset)
            assert callable(_backend.operating_point)
            assert callable(_backend.transient)
            assert callable(_backend.inject_state)
            assert callable(_backend.get_vector)
            assert _backend.last_benchmark is None
            print(f"{type(_backend).__name__}: Simulator contract OK")
    except Exception as e:  # pragma: no cover
        print(f"Backend contract check failed: {e}")
